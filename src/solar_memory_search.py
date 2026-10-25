"""열 이력과 태양 위치의 결합 및 관측소 좌표 대체를 구분한다."""
import pandas as pd
from src.thermal_extended import feature_table as thermal_features
from src.combined_thermal_history import feature_table as combined_features


def feature_table(frame,kind):
    if kind=='history_asos_solar':
        base=thermal_features(frame,'thermal_history')
    elif kind in ['combined_asos_solar','combined_target_solar']:
        base=combined_features(frame,'combined_thermal_history')
    else:raise ValueError('Unknown solar-memory input set')
    columns=['asos_solar_altitude_deg','asos_solar_sine_positive'] if kind.endswith('asos_solar') else ['solar_altitude_deg','solar_sine_positive']
    return pd.concat([base,frame[columns].astype(float)],axis=1)
