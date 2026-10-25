"""열·수분 후보의 용량·정규화·입력 제거 대조. 기존 탐색 코드는 보존한다."""
import numpy as np
import pandas as pd
from src.extended_search import estimator as base_estimator
from src.thermal_extended import feature_table as thermal_features


def feature_table(frame, kind='thermal'):
    if kind in ['weather','derived','history','thermal','thermal_distance','thermal_history']:
        return thermal_features(frame, kind)
    x = thermal_features(frame, 'thermal')
    if kind == 'thermal_no_ground':
        return x.drop(columns=['asos_ground_temp', 'ground_air_gap'])
    if kind == 'thermal_ground_only':
        return pd.concat([thermal_features(frame, 'weather'), x[['asos_ground_temp', 'ground_air_gap']]], axis=1)
    if kind != 'thermal_memory':
        raise ValueError('Unknown thermal refinement feature set')
    # 관측 지점의 노면온도 이력은 쓰지 않는다. 시간 t의 값도 창에 포함하지 않는다.
    parts = []
    for _, part in frame.groupby(['station', 'winter'], sort=False):
        ordered = part.sort_values('time')
        values = ordered.set_index('time')[['asos_ground_temp', 'asos_solar_mj_m2', 'asos_cloud_tenths']]
        result = pd.DataFrame(index=values.index)
        for hours in [1, 3, 12]:
            window = values.rolling(f'{hours}h', closed='left', min_periods=int(np.ceil(hours * 6 * .8)))
            for column in values:
                result[f'{column}_prior_{hours}h_mean'] = window[column].mean()
        result.index = ordered.index
        parts.append(result)
    return pd.concat([x, pd.concat(parts).reindex(frame.index)], axis=1)


def estimator(spec, seed=20261024, threads=2):
    model = base_estimator(spec, seed, threads)
    if spec['family'] != 'hgb':
        raise ValueError('Refinement currently permits HGB only')
    allowed = {'min_samples_leaf', 'l2_regularization', 'learning_rate', 'max_bins'}
    overrides = spec.get('overrides', {})
    if set(overrides) - allowed:
        raise ValueError('Unknown refinement override')
    return model.set_params(**overrides)
