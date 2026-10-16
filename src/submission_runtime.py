"""학습과 분리된 기상 입력 계약·추론·기준표. 정답 열과 미정의 판정을 구별한다."""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import joblib
from threadpoolctl import threadpool_limits
try:
    from .submission_io import read_weather
except ImportError:  # 제출 묶음의 code/runtime.py로 실행할 때
    from submission_io import read_weather

FEATURES = ('asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_wind_speed', 'aws_rain_15m', 'aws_dewpoint',
            'aws_age_minutes', 'asos_age_minutes', 'hour_sin', 'hour_cos', 'season_sin', 'season_cos')
WATER = ('aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm')
FORBIDDEN = {'road_temp', 'ice', 'state_raw', 'state', 'observed_ice', 'actual_ice', 'target', 'label'}
SENTINELS = (-999., -99.9, -99.2, -99.7)


def prepare_weather(frame):
    if FORBIDDEN.intersection(str(c).strip().lower() for c in frame.columns):
        raise ValueError('Target measurements cannot enter inference inputs')
    required = {'station', 'time', *FEATURES, *WATER}
    if not required <= set(frame.columns) or frame.empty or frame.columns.duplicated().any():
        raise ValueError('Nonempty weather input with unique declared columns required')
    f = frame.loc[:, ['station', 'time', *FEATURES, *[c for c in WATER if c not in FEATURES]]].copy()
    if f.station.isna().any(): raise ValueError('Missing station identity')
    f.station = f.station.astype(str).str.strip()
    f.station = f.station.str.replace(r'^([0-9]+)\.0$', r'\1', regex=True)
    if f.station.str.lower().isin(['', 'nan', 'none', 'null', '<missing>']).any():
        raise ValueError('Empty station identity')
    f.time = pd.to_datetime(f.time, errors='raise')
    if f.time.dt.tz is not None: f.time = f.time.dt.tz_convert('Asia/Seoul').dt.tz_localize(None)
    if f.time.isna().any() or ((f.time.dt.minute%10 != 0) | (f.time.dt.second != 0) |
            (f.time.dt.microsecond != 0) | (f.time.dt.nanosecond != 0)).any() or f.duplicated(['station','time']).any():
        raise ValueError('Unique exact ten-minute KST identities required')
    for c in required-{'station', 'time'}:
        f[c] = pd.to_numeric(f[c], errors='raise').replace(list(SENTINELS), np.nan)
        if np.isinf(f[c]).any(): raise ValueError('Infinite weather input')
    for c in ['aws_age_minutes', 'asos_age_minutes']:
        if f[c].dropna().le(0).any():
            raise ValueError('Weather must strictly precede the target time')
    if not f.aws_humidity.dropna().between(0,100).all(): raise ValueError('Invalid humidity')
    for c in ['aws_wind_speed', 'aws_rain_15m', 'rain15_max_3h', 'asos_snow_cm']:
        if f[c].dropna().lt(0).any(): raise ValueError('Negative moisture or wind observation')
    for c in ['hour_sin','hour_cos','season_sin','season_cos']:
        if f[c].isna().any() or not f[c].between(-1,1).all(): raise ValueError('Finite cyclic time features required')
    # 제공 입력의 계산 규약을 그대로 유지하고 나이를 명시적으로 검사한다.
    asos_valid = f.asos_age_minutes.gt(0) & f.asos_age_minutes.le(60) & f.asos_air_temp.notna()
    aws_stale = ~(f.aws_age_minutes.gt(0) & f.aws_age_minutes.le(60))
    f.loc[aws_stale, ['aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint']] = np.nan
    return f, asos_valid, aws_stale


def infer(frame, models):
    f, asos_valid, aws_stale = prepare_weather(frame)
    values = []
    with threadpool_limits(limits=2):
        for model in models:
            if list(model.feature_names_in_) != list(FEATURES): raise ValueError('Model feature order mismatch')
            values.append(np.asarray(model.predict(f[list(FEATURES)]), float))
    if len(values) != 2 or any(v.shape != (len(f),) or not np.isfinite(v).all() for v in values):
        raise ValueError('Exactly two complete temperature components required')
    temp = (values[0]+values[1])/2
    temp[~asos_valid] = np.nan
    w = f[list(WATER)].to_numpy(float)
    known_water = ~np.isnan(w).all(axis=1)
    wet = (w[:,0] >= temp) | (w[:,1] > 0) | (w[:,2] > 0)
    valid = asos_valid.to_numpy() & known_water
    ice = pd.array(np.where(valid, ((temp <= 0)&wet).astype(float), np.nan), dtype='Int64')
    both = (np.maximum(values[0], values[1]) <= 0) & wet
    condition = np.where(~valid, 'insufficient_input', np.where((temp <= 0)&wet,
        np.where(both, 'cold_wet_consensus', 'cold_wet_disagreement'), 'criterion_not_met'))
    out = f[['station','time']].copy()
    out['estimated_road_temp_c'] = temp
    out['temperature_component_spread_c'] = np.abs(values[0]-values[1])
    out['predicted_ice'] = ice
    out['condition_evidence'] = condition
    out['temperature_status'] = np.where(asos_valid, 'estimated', 'insufficient_asos')
    out['moisture_status'] = np.where(known_water, 'observed_weather', 'insufficient_moisture')
    out['aws_status'] = np.where(aws_stale, 'missing_or_stale', 'within_60_minutes')
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--models', type=Path, default=Path(__file__).resolve().parent.parent/'model')
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Existing prediction is preserved')
    data = read_weather(args.input)
    models = [joblib.load(args.models/(name+'.joblib')) for name in ['weather12_mse300','weather12_mae300']]
    result = infer(data, models)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix.lower() == '.parquet': result.to_parquet(args.output, index=False)
    else: result.to_csv(args.output, index=False, encoding='utf-8-sig', na_rep='')
    print(json.dumps({'status':'candidate_inference_complete', 'rows':len(result), 'temperature_available':int(result.estimated_road_temp_c.notna().sum()),
        'ice_available':int(result.predicted_ice.notna().sum()), 'official_csv_schema':False, 'operational_warning':False}, ensure_ascii=False))


if __name__ == '__main__': main()
