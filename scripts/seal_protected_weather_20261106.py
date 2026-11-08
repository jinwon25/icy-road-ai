"""고정 기상 모형으로 지정 세 지점 예측을 만들고 실측 기상 열을 열기 전에 봉인한다."""
from pathlib import Path
from datetime import datetime, timezone
import json, sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.segment_exposure import WeatherOnlySources
from src.road_weather_points import RoadWeatherPoints
from src.weather_history_runtime import predict_weather_history
from src.wind_network_runtime import predict_wind_network
from src.road_weather_transfer import baselines
from src.offline_runtime import deny_network

W=ROOT/'outputs/private/judging_upgrade_20261106'
B=ROOT/'outputs/private/competition_submission/icy_road_model'
STATIONS=['12410','23402','33411']

def write(path,value):
    with path.open('x',encoding='utf8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')

def main():
    out=W/'protected_weather';out.mkdir()
    plan=dict(created_utc=datetime.now(timezone.utc).isoformat(),stations=STATIONS,
        periods=[['2024-11-01','2025-03-01'],['2025-11-01','2026-03-01']],
        question='固定済み 기상 모형의 지정 검증 지점 전이 성능과 단순 관측소 기준의 차이',
        targets=['air_temperature','relative_humidity','wind_speed'],
        models_frozen_before_20261106=True,new_training=False,new_threshold_selection=False,
        weather_targets_read_before_this_prediction_seal=False,
        other_protected_state_and_surface_temperature_previously_opened=True,
        baselines=['strict_past_asos_60min','nearest_aws_15min_else_asos'],
        metrics=['bias_prediction_minus_observed','mae','rmse'],
        aggregation='site and winter rows plus equally weighted 3-site mean; common finite pairs for each target and all methods',
        target_bounds={'air_temperature':[-80,60],'relative_humidity':[0,100],'wind_speed':[0,100]},
        missing_codes=[-999.,-99.9,-99.2,-99.7],
        uncertainty='paired 7-day circular block bootstrap; same dates shared across sites; site macro MAE delta; 2000 resamples, seed 61106; descriptive sensitivity for these 3 sites',
        no_promotion_or_model_selection_from_protected_weather=True)
    # 이 계획과 아래 파일에는 도로 관측 목표 열이 없다.
    plan['question']=plan['question'].replace('固定済み','고정된')
    write(out/'plan.json',plan)
    config=json.loads((ROOT/'config/weather_segment_projection_20261031.json').read_text('utf8'))
    source=ROOT/config['weather_sources'];extra=ROOT/config['input_preparation']/'asos_supplementary.parquet'
    aws=pd.read_parquet(source/'aws.parquet')
    weather=WeatherOnlySources(aws,pd.read_parquet(source/'asos.parquet'),
        pd.read_csv(source/'weather_coordinates.csv',dtype={'station_id':str}))
    times=pd.DatetimeIndex(np.concatenate([pd.date_range(a,b,freq='10min',inclusive='left').values for a,b in plan['periods']]))
    builder=RoadWeatherPoints(weather,pd.read_parquet(extra),times)
    static=ROOT/'outputs/private/releases/20261007/outputs/private/frozen_assessment_v1/static_metadata.csv'
    points=pd.read_csv(static,usecols=['station','lat','lon'],dtype={'station':str})
    points=points.loc[points.station.isin(STATIONS)].sort_values('station')
    assert points.station.tolist()==STATIONS
    mappings={};frames=[]
    for p in points.itertuples():
        f,mapping=builder.build(p.lat,p.lon);f.insert(0,'station',p.station)
        frames.append(f);mappings[p.station]=mapping
    f=pd.concat(frames,ignore_index=True)
    f.to_parquet(out/'weather_inputs.parquet',index=False)
    points.to_csv(out/'points.csv',index=False)
    h=B/'weather/humidity/model'
    result=predict_weather_history(f,h/'weather_v1',h/'humidity_history_v1')
    coordinates=pd.read_csv(B/'weather/wind/data/aws_coordinates.csv',dtype={'station':str})
    wind=predict_wind_network(f,points,aws,coordinates,B/'weather/wind/model')
    assert result[['station','time']].equals(wind[['station','time']])
    result['estimated_wind_speed_ms']=wind.estimated_wind_speed_ms
    result['estimated_wind_speed_ms_available']=wind.estimated_wind_speed_ms_available
    for target in plan['targets']:
        a,b=baselines(f,target);result['asos_'+target]=a;result['aws_'+target]=b
    result.to_parquet(out/'predictions.parquet',index=False)
    write(out/'mapping.json',mappings)
    frozen=list((h).rglob('*.joblib'))+list((h).rglob('metadata.json'))+list((B/'weather/wind/model').glob('*'))
    sources=[ROOT/'config/weather_segment_projection_20261031.json',source/'aws.parquet',source/'asos.parquet',source/'weather_coordinates.csv',extra,static,
        B/'weather/wind/data/aws_coordinates.csv',Path(__file__),ROOT/'src/road_weather_points.py',ROOT/'src/weather_history_runtime.py',ROOT/'src/wind_network_runtime.py']+frozen
    write(out/'prediction_seal.json',dict(sealed_utc=datetime.now(timezone.utc).isoformat(),rows=len(result),stations=STATIONS,
        files={p.name:sha(p) for p in out.iterdir() if p.is_file()},
        input_signatures={p.relative_to(ROOT).as_posix():sha(p) for p in sources},
        weather_targets_read=False,training=False))
    print(json.dumps(dict(status='protected_weather_predictions_sealed',rows=len(result),seal_sha256=sha(out/'prediction_seal.json')),ensure_ascii=False),flush=True)

if __name__=='__main__':
    with deny_network():main()
