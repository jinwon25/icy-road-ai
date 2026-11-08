"""노면 상태를 보조 학습 정답으로 묶는다. 추론 입력에는 상태를 넣지 않는다."""
import numpy as np
import pandas as pd
from src.validation import normalize_state

# 출력 점수의 3번 클래스만 Ice. 다른 유효 상태를 양성으로 바꾸지 않는다.
STATE_GROUPS={1:0,10:0,2:1,11:1,12:1,13:1,14:1,3:2,4:3,15:4}
NAMES={0:'dry',1:'liquid_or_treated',2:'snow',3:'ice',4:'uncertain'}


def state_targets(raw,ice):
    code=pd.to_numeric(pd.Series(raw),errors='coerce')
    target=code.map(STATE_GROUPS)
    original=pd.Series(raw).map(normalize_state).to_numpy(float,na_value=np.nan)
    expected=np.asarray(ice,float)
    np.testing.assert_array_equal(original,expected)
    np.testing.assert_array_equal(target.eq(3).to_numpy(),expected==1)
    np.testing.assert_array_equal(target.isna().to_numpy(),~np.isfinite(expected))
    return target.to_numpy(float)


def state_day_weights(frame):
    if not frame.state_target.isin(range(5)).all():
        raise ValueError('Known state groups only')
    f=frame[['station','winter','time','state_target']].copy()
    f['day']=f.time.dt.normalize()
    size=f.groupby(['station','winter','day','state_target']).station.transform('size').to_numpy(float)
    classes=f.groupby(['station','winter','day']).state_target.transform('nunique').to_numpy(float)
    days=f.groupby(['station','winter']).day.transform('nunique').to_numpy(float)
    w=1/(size*classes*days)
    return w/w.mean()
