"""기온 대비 노면온도 편차와 기상 입력만 사용하는 공간 전이 후보."""
import numpy as np
import pandas as pd

from src.validation import PROTECTED_STATIONS


WEATHER_FEATURES = [
    'asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_wind_speed',
    'aws_rain_15m', 'aws_dewpoint', 'aws_age_minutes', 'asos_age_minutes',
    'aws_distance_km', 'asos_distance_km', 'hour_sin', 'hour_cos',
    'season_sin', 'season_cos',
]
THERMAL_FEATURES = WEATHER_FEATURES + [
    'asos_ground_temp', 'asos_cloud_tenths', 'asos_solar_mj_m2',
    'asos_rain_mm', 'asos_snow_cm', 'asos_humidity', 'air_min_3h',
    'rain15_max_3h', 'air_dewpoint_gap', 'ground_air_gap',
]
CANDIDATES = {
    'residual_weather14': (WEATHER_FEATURES, True),
    'direct_thermal24': (THERMAL_FEATURES, False),
    'residual_thermal24': (THERMAL_FEATURES, True),
}
LOSS_CANDIDATES = {
    'weather_mae100': (WEATHER_FEATURES, False),
    'weather_mse300': (WEATHER_FEATURES, False),
    'weather_mae300': (WEATHER_FEATURES, False),
}
MODEL_OVERRIDES = {
    'weather_mae100': {'loss': 'absolute_error', 'max_iter': 100},
    'weather_mse300': {'loss': 'squared_error', 'max_iter': 300},
    'weather_mae300': {'loss': 'absolute_error', 'max_iter': 300},
}


def candidate_spec(candidate):
    return (CANDIDATES | LOSS_CANDIDATES)[candidate]


def validate_development(frame):
    """정답을 가진 첫 겨울 23개 개발 지점 외 자료의 사용을 차단한다."""
    if frame.empty or frame.duplicated(['station', 'time']).any():
        raise ValueError('Empty or duplicate development rows')
    if set(frame.station.astype(str)) & PROTECTED_STATIONS:
        raise ValueError('Protected station in development')
    times = pd.to_datetime(frame.time)
    if times.isna().any() or times.dt.tz is not None:
        raise ValueError('Naive KST development timestamps required')
    if not (times.ge('2024-11-01') & times.lt('2025-03-01')).all():
        raise ValueError('Only first-winter development outcomes permitted')
    if (times.dt.minute.mod(10).ne(0) | times.dt.second.ne(0)
            | times.dt.microsecond.ne(0)).any():
        raise ValueError('Exact ten-minute observations required')


def training_arrays(frame, candidate, forbidden=()):
    validate_development(frame)
    if set(frame.station.astype(str)) & set(map(str, forbidden)):
        raise ValueError('Held-out group entered fitting')
    names, residual = candidate_spec(candidate)
    if not np.isfinite(frame.road_temp).all() or not np.isfinite(frame.asos_air_temp).all():
        raise ValueError('Identical finite training domain required')
    x = frame[names].astype(float)
    if np.isinf(x.to_numpy()).any():
        raise ValueError('Infinite weather predictor')
    y = frame.road_temp.to_numpy(dtype=float)
    if residual:
        y = y - frame.asos_air_temp.to_numpy(dtype=float)
    return x, y


def predict_temperature(model, frame, candidate):
    names, residual = candidate_spec(candidate)
    x = frame[names].astype(float)
    if np.isinf(x.to_numpy()).any():
        raise ValueError('Infinite weather predictor')
    prediction = np.asarray(model.predict(x), dtype=float)
    if prediction.shape != (len(frame),) or not np.isfinite(prediction).all():
        raise ValueError('Incomplete model predictions')
    if residual:
        prediction += frame.asos_air_temp.to_numpy(dtype=float)
    return np.where(np.isfinite(frame.asos_air_temp), prediction, np.nan)


def regression_report(frame, prediction):
    prediction = np.asarray(prediction, dtype=float)
    if prediction.shape != (len(frame),):
        raise ValueError('Prediction alignment mismatch')
    valid = np.isfinite(frame.road_temp) & np.isfinite(prediction)

    def metric(mask):
        err = prediction[mask] - frame.road_temp.to_numpy()[mask]
        return {'n': int(len(err)), 'mae': float(np.abs(err).mean()) if len(err) else None,
                'rmse': float(np.sqrt(np.mean(err ** 2))) if len(err) else None,
                'bias': float(err.mean()) if len(err) else None}

    stations = {str(st): metric(np.asarray(valid & frame.station.eq(st)))
                for st in sorted(frame.station.unique())}
    supported = [r for r in stations.values() if r['n']]
    return {'pooled': metric(np.asarray(valid)), 'stations': stations,
            'station_macro': {m: float(np.mean([r[m] for r in supported]))
                              if supported else None for m in ['mae', 'rmse', 'bias']},
            'near_freezing': metric(np.asarray(valid & frame.road_temp.between(-2, 2)))}


def select_temperature(reports, baseline='direct_weather14', maximum_station_harm=.05, candidate_names=None):
    """내부 그룹에서 평균·결빙점 부근·각 지점의 동일 분모를 비교한다."""
    base = reports[baseline]
    eligible = []
    for candidate in (list(CANDIDATES) if candidate_names is None else candidate_names):
        r = reports[candidate]
        if set(r['stations']) != set(base['stations']):
            raise ValueError('Station population changed')
        if any(r['stations'][s]['n'] != base['stations'][s]['n'] for s in base['stations']):
            raise ValueError('Candidate valid-row denominator changed')
        if r['near_freezing']['n'] != base['near_freezing']['n']:
            raise ValueError('Near-freezing denominator changed')
        if not all(r['station_macro'][m] < base['station_macro'][m] - 1e-12
                   for m in ['mae', 'rmse']):
            continue
        if any(r['stations'][s]['mae'] > base['stations'][s]['mae'] * (1 + maximum_station_harm) + 1e-12
               for s in base['stations']):
            continue
        if r['near_freezing']['n'] and r['near_freezing']['mae'] > base['near_freezing']['mae'] + 1e-12:
            continue
        eligible.append(candidate)
    return min(eligible, key=lambda c: (reports[c]['station_macro']['mae'],
                                       reports[c]['station_macro']['rmse'], c)) if eligible else baseline
