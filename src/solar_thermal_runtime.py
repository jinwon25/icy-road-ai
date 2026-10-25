"""태양 위치를 쓰는 후보의 실행 계약. 기상관측소와 대상 위치를 구별한다."""
import numpy as np
import pandas as pd
from .advanced_thermal_runtime import advanced_predictors

GEOMETRY=('asos_solar_altitude_deg','asos_solar_sine_positive','solar_altitude_deg','solar_sine_positive')


def temperature_predictors(frame,kind):
    if kind in ['thermal','thermal_history','combined_thermal_history']:
        return advanced_predictors(frame,kind)
    if kind not in ['history_asos_solar','combined_asos_solar','combined_target_solar','history_solar']:
        raise ValueError('Unsupported temperature input contract')
    base='combined_thermal_history' if kind.startswith('combined_') else 'thermal_history'
    x,valid,stale=advanced_predictors(frame,base)
    names=list(GEOMETRY[:2] if kind.endswith('asos_solar') else GEOMETRY[2:])
    if not set(names)<=set(frame):raise ValueError('Declared solar position inputs required')
    solar=frame[names].apply(pd.to_numeric,errors='raise').astype(float)
    if not np.isfinite(solar.to_numpy()).all() or not solar[names[0]].between(-90,90).all():
        raise ValueError('Finite solar altitude in degrees required')
    expected=np.maximum(0,np.sin(np.deg2rad(solar[names[0]].to_numpy())))
    if not np.allclose(solar[names[1]],expected,rtol=0,atol=1e-12):raise ValueError('Inconsistent solar geometry')
    return pd.concat([x,solar],axis=1),valid,stale
