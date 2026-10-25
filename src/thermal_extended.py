"""추가 기상 관측의 사용 가능성을 대조하는 열·수분 특징. 도로 정답·ID 특징 제외."""
import numpy as np
from src.extended_search import feature_table as base_features
from src.temperature_transfer import THERMAL_FEATURES


def feature_table(frame,kind='thermal'):
    if kind in ['weather','derived','history']:return base_features(frame,kind)
    x=base_features(frame,'history' if kind=='thermal_history' else 'weather')
    extras=[c for c in THERMAL_FEATURES if c not in x and c not in ['aws_distance_km','asos_distance_km']]
    for column in extras:x[column]=frame[column].astype(float)
    if kind=='thermal_distance':
        for column in ['aws_distance_km','asos_distance_km']:x[column]=frame[column].astype(float)
    elif kind not in ['thermal','thermal_history']:raise ValueError('Unknown thermal feature set')
    if np.isinf(x.to_numpy()).any():raise ValueError('Infinite thermal predictor')
    return x
