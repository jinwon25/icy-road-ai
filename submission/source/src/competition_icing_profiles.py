"""공식 점수 검토와 기존 v2의 선택 목적을 분리하는 명시적 실행 프로필."""
import numpy as np
import pandas as pd
from src.submission_runtime import prepare_weather

PROFILES=('preserved_v2','score_priority_asos_zero')


def apply_icing_profile(weather,predictions,profile):
    if profile not in PROFILES:raise ValueError('Explicit known icing profile required')
    source,valid,_=prepare_weather(weather)
    pd.testing.assert_frame_equal(source[['station','time']],predictions[['station','time']],check_exact=True)
    if profile=='preserved_v2':return predictions.copy()
    result=predictions.copy()
    for old,new in [('predicted_ice','preserved_v2_predicted_ice'),('condition_evidence','preserved_v2_condition_evidence'),
        ('icing_reference_temperature_c','preserved_v2_reference_temperature_c'),
        ('icing_reference_component_spread_c','preserved_v2_reference_component_spread_c')]:
        result[new]=predictions[old]
    available=predictions.predicted_ice.notna().to_numpy()
    if not np.all(valid.to_numpy()[available]):raise ValueError('Original available prediction lacks valid ASOS')
    air=source.asos_air_temp.to_numpy(float)
    result['predicted_ice']=pd.array(np.where(available,air<=0,np.nan),dtype='Int64')
    result['icing_reference_temperature_c']=np.where(available,air,np.nan)
    result['icing_reference_component_spread_c']=np.where(available,0.,np.nan)
    result['icing_policy']='score_priority_asos_zero_v1'
    result['condition_evidence']=np.where(~available,'insufficient_input',np.where(air<=0,'asos_air_le_zero','asos_air_above_zero'))
    assert result.predicted_ice.isna().equals(predictions.predicted_ice.isna())
    return result
