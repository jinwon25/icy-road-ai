"""온도와 수분 대용값의 물리 조건을 표현한다. Ice 확률·사고 위험 점수가 아니다."""
import numpy as np


def cold_moisture_condition(temperature,dewpoint,rain15_max24):
    t,dew,rain=np.broadcast_arrays(np.asarray(temperature,float),np.asarray(dewpoint,float),np.asarray(rain15_max24,float))
    wet=(np.isfinite(rain)&(rain>0))|(np.isfinite(dew)&(dew>=t))
    support_known=wet|(np.isfinite(dew)&np.isfinite(rain))
    valid=np.isfinite(t)&((t>0)|support_known)
    return np.where(valid,((t<=0)&wet).astype(float),np.nan)
