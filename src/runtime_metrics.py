"""제출 추론의 null을 유효 음성으로 바꾸지 않는 두 겨울 일별 평가."""
import numpy as np
from src.two_winter import daily


def runtime_daily(frame,prediction,minimum=144):
    p=np.asarray(prediction,dtype=float)
    if p.shape!=(len(frame),) or not np.isin(p[np.isfinite(p)],[0.,1.]).all() or np.isinf(p).any():
        raise ValueError('Aligned binary-or-missing prediction required')
    absent=~np.isfinite(p);f=frame.copy()
    positive_missing=int((absent & frame.ice.eq(1).to_numpy()).sum())
    # 원 집계기는 정의된 예측만 받는다. 결측 쌍은 정답도 평가 대상에서 제외한다.
    # 임시 0은 혼동행렬이나 유효 관측량에 절대로 포함되지 않는다.
    f.loc[absent,'ice']=np.nan
    report,stations,days=daily(f,np.where(absent,0,p),minimum)
    report['missing_prediction_rows']=int(absent.sum())
    report['known_positive_rows_without_prediction']=positive_missing
    return report,stations,days
