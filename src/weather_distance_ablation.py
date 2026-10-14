"""기상망·학습 길이를 유지하고 거리 입력 두 개만 제거하는 개발 가안."""
import numpy as np

from src.evidence_review import review_domain
from src.temperature_transfer import WEATHER_FEATURES

REMOVED_FEATURES = ('aws_distance_km', 'asos_distance_km')
DISTANCE_FREE_FEATURES = tuple(f for f in WEATHER_FEATURES if f not in REMOVED_FEATURES)
CANDIDATE = 'weather12_no_distance'


def training_values(frame, forbidden=()):
    frame = review_domain(frame)
    if set(frame.station) & set(map(str, forbidden)):
        raise ValueError('Held-out station entered fitting')
    if not np.isfinite(frame.road_temp).all() or not np.isfinite(frame.asos_air_temp).all():
        raise ValueError('Same finite training domain required')
    x = frame[list(DISTANCE_FREE_FEATURES)].astype(float)
    if np.isinf(x.to_numpy()).any():
        raise ValueError('Infinite weather input')
    return x, frame.road_temp.to_numpy(dtype=float)


def predict(model, frame):
    frame = review_domain(frame)
    x = frame[list(DISTANCE_FREE_FEATURES)].astype(float)
    if np.isinf(x.to_numpy()).any():
        raise ValueError('Infinite weather input')
    prediction = np.asarray(model.predict(x), dtype=float)
    if prediction.shape != (len(frame),) or not np.isfinite(prediction).all():
        raise ValueError('Incomplete weather prediction')
    return np.where(np.isfinite(frame.asos_air_temp), prediction, np.nan)
