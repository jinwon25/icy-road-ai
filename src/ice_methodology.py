"""목표 관측을 쓰지 않는 결빙 분류 대안과 엄격한 과거 기상 입력."""
import numpy as np
import pandas as pd

from src.joint_surface import FEATURES
from src.method_blending import domain

CANDIDATES = ('hgb_long300', 'hgb_no_distance', 'hgb_history', 'hgb_balanced', 'catboost400', 'hurdle_non_dry')
HISTORY_COLUMNS = ('estimated_weather_temp', 'aws_air_temp', 'aws_humidity', 'aws_dewpoint', 'aws_rain_15m', 'aws_wind_speed')
HISTORY_FEATURES = [f'{c}_prior_mean_{m}m' for c in HISTORY_COLUMNS for m in (60, 180)] + [f'{c}_change_60m' for c in HISTORY_COLUMNS]
NO_DISTANCE = [c for c in FEATURES if c not in ('aws_distance_km', 'asos_distance_km')]


def causal_history(frame):
    """같은 지점의 [t-w,t) 평균: 80% 관측이 있어야 제공하며 미래 보간하지 않는다."""
    domain(frame)
    output = pd.DataFrame(np.nan, index=frame.index, columns=HISTORY_FEATURES)
    if frame.index.duplicated().any():
        raise ValueError('Unique row index required')
    for _, part in frame.groupby('station', sort=False):
        part = part.sort_values('time')
        values = part[list(HISTORY_COLUMNS)].astype(float).copy()
        if np.isinf(values.to_numpy()).any():
            raise ValueError('Infinite history input')
        values.index = pd.DatetimeIndex(part.time)
        for c in HISTORY_COLUMNS:
            for minutes in (60, 180):
                window = values[c].rolling(f'{minutes}min', closed='left', min_periods=1)
                mean = window.mean().where(window.count() >= np.ceil(.8*minutes/10))
                output.loc[part.index, f'{c}_prior_mean_{minutes}m'] = mean.to_numpy()
            prior = values[c].reindex(values.index-pd.Timedelta(minutes=60)).to_numpy()
            output.loc[part.index, f'{c}_change_60m'] = values[c].to_numpy()-prior
    return output


def candidate_features(frame, candidate, history=None):
    if candidate not in CANDIDATES:
        raise ValueError('Unknown fixed candidate')
    x = frame[NO_DISTANCE if candidate == 'hgb_no_distance' else FEATURES].copy()
    if candidate == 'hgb_history':
        if history is None or not history.index.equals(frame.index) or list(history.columns) != HISTORY_FEATURES:
            raise ValueError('Aligned strictly prior history required')
        x = pd.concat([x, history], axis=1)
    if np.isinf(x.to_numpy(float)).any():
        raise ValueError('Infinite classifier feature')
    return x


def training_weights(labels, balanced=False, positive_weight=20.):
    y = np.asarray(labels)
    if y.ndim != 1 or not np.isin(y, [0, 1]).all() or set(y) != {0, 1}:
        raise ValueError('Both defined binary classes required')
    if balanced:
        counts = np.bincount(y.astype(int), minlength=2)
        return len(y)/(2*counts[y.astype(int)])
    if not np.isfinite(positive_weight) or positive_weight <= 0:
        raise ValueError('Positive finite class multiplier required')
    return np.where(y == 1, positive_weight, 1.)


def hurdle_labels(raw):
    """비건조는 01을 제외한 공식 정의 상태의 보조 구분이지 물리적 수분 정답이 아니다."""
    code = pd.to_numeric(pd.Series(raw), errors='coerce').to_numpy(float)
    if not np.isin(code, [1, 2, 3, 4, 10, 11, 12, 13, 14, 15]).all():
        raise ValueError('Only defined official training states accepted')
    return (code != 1).astype(int), (code == 4).astype(int)


def binary_score(model, x):
    probabilities = np.asarray(model.predict_proba(x))
    classes = np.asarray(model.classes_)
    positive = np.flatnonzero(classes == 1)
    if len(positive) != 1 or probabilities.shape != (len(x), len(classes)) or not np.isfinite(probabilities).all() or not ((probabilities >= 0) & (probabilities <= 1)).all() or not np.allclose(probabilities.sum(axis=1), 1):
        raise ValueError('Invalid binary score')
    return probabilities[:, positive[0]]
