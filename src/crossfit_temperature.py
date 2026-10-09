"""개발 지점별 교차 적합 온도 입력. 대상 온도 정답을 분류 입력에서 격리한다."""
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from src.validation import assert_training_stations

WEATHER_FEATURES = ['asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_wind_speed',
                    'aws_rain_15m', 'aws_dewpoint', 'aws_age_minutes', 'asos_age_minutes',
                    'aws_distance_km', 'asos_distance_km', 'hour_sin', 'hour_cos', 'season_sin', 'season_cos']
ESTIMATED_FEATURES = ['estimated_weather_temp', 'estimated_blend_temp', 'estimated_surface_dewpoint_gap', 'estimated_surface_air_gap']


def fit_weather(train, forbidden, train_before):
    assert_training_stations(train.station.unique())
    if set(train.station) & set(forbidden) or train.time.max() >= pd.Timestamp(train_before):
        raise ValueError('Forbidden temperature training partition')
    eligible = train.loc[train.road_temp.notna() & train.asos_air_temp.notna()]
    if len(eligible) == 0 or eligible.station.nunique() < 2:
        raise ValueError('Insufficient temperature training stations')
    model = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                          StandardScaler(), Ridge(alpha=100.))
    model.fit(eligible[WEATHER_FEATURES], eligible.road_temp)
    manifest = {'training_stations': sorted(eligible.station.unique()), 'training_rows': len(eligible),
                'train_last_time': str(eligible.time.max()), 'forbidden': sorted(forbidden)}
    return model, manifest


def predict_weather(model, target):
    assert_training_stations(target.station.unique())
    values = pd.Series(np.nan, index=target.index, dtype=float)
    available = target.asos_air_temp.notna()
    values.loc[available] = model.predict(target.loc[available, WEATHER_FEATURES]) if available.any() else []
    return values


def crossfit_weather(train, forbidden, train_before):
    """지점 ID 정렬 후 3그룹을 고정하며 자기 그룹의 정답·전처리는 참조하지 않는다."""
    assert_training_stations(train.station.unique())
    ids = sorted(train.station.unique())
    if len(ids) < 3 or train.duplicated(['station', 'time']).any():
        raise ValueError('Invalid crossfit grid')
    scores = pd.Series(np.nan, index=train.index, dtype=float)
    models = []; manifests = []
    for group in range(3):
        held = set(ids[group::3]); mask = train.station.isin(held)
        model, manifest = fit_weather(train.loc[~mask], set(forbidden) | held, train_before)
        scores.loc[mask] = predict_weather(model, train.loc[mask])
        manifest['prediction_stations'] = sorted(held)
        if set(manifest['training_stations']) & held:
            raise AssertionError('Temperature target station leaked')
        models.append(model); manifests.append(manifest)
    return scores, models, manifests


def estimated_inputs(frame, thermal, weather):
    """ASOS 영역 밖은 미정의. 인접 온도가 없으면 검증한 기상 온도만 사용한다."""
    if not frame.index.equals(thermal.index) or not frame.index.equals(weather.index):
        raise ValueError('Misaligned temperature inputs')
    blend = weather.copy()
    paired = weather.notna() & thermal.near_road_temp.notna()
    blend.loc[paired] = .5 * weather.loc[paired] + .5 * thermal.loc[paired, 'near_road_temp']
    return pd.DataFrame({'estimated_weather_temp': weather, 'estimated_blend_temp': blend,
                         'estimated_surface_dewpoint_gap': blend - frame.aws_dewpoint,
                         'estimated_surface_air_gap': blend - frame.aws_air_temp}, index=frame.index)[ESTIMATED_FEATURES]
