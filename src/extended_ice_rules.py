"""두 겨울 규칙 탐색의 날짜·지점 분모와 과거 연속조건. 학습 모델은 사용하지 않는다."""
from itertools import product
import numpy as np
import pandas as pd
from src.two_winter import validate


def policies(plan):
    return [dict(source=s,threshold=t,moisture=m,slots=n) for s,t,m,n in product(plan['sources'],plan['thresholds'],plan['moisture'],plan['consecutive_slots'])]


def consecutive(frame,raw,slots):
    validate(frame);v=np.asarray(raw,bool)
    if slots not in [1,3,6] or v.shape!=(len(frame),):raise ValueError('Declared aligned condition required')
    if slots==1:return v.copy()
    result=np.zeros(len(frame),bool)
    for positions in frame.groupby('station',sort=False).indices.values():
        positions=np.asarray(positions);positions=positions[np.argsort(frame.iloc[positions].time.to_numpy())]
        times=frame.iloc[positions].time.to_numpy(dtype='datetime64[ns]');a=v[positions]
        if len(a)<slots:continue
        total=np.r_[0,np.cumsum(a,dtype=np.int64)]
        result[positions[slots-1:]]=(total[slots:]-total[:-slots]==slots)&(times[slots-1:]-times[:1-slots]==np.timedelta64((slots-1)*10,'m'))
    return result


def raw_policy(frame,rain3h,spec):
    if spec['source']=='asos':cold=frame.asos_air_temp.to_numpy()
    elif spec['source']=='aws':cold=frame.aws_air_temp.to_numpy()
    elif spec['source']=='mean':cold=(frame.asos_air_temp.to_numpy()+frame.aws_air_temp.to_numpy())/2
    else:raise ValueError('Unknown source')
    m=spec['moisture'];rh=frame.aws_humidity.to_numpy();gap=frame.aws_air_temp.to_numpy()-frame.aws_dewpoint.to_numpy()
    if m=='none':wet=np.ones(len(frame),bool)
    elif m.startswith('humidity'):wet=rh>=int(m[8:10])
    elif m.startswith('dew'):wet=gap<=int(m[3])
    else:raise ValueError('Unknown moisture gate')
    if m.endswith('_or_rain3h'):wet=wet|(np.asarray(rain3h)>0)
    return (cold<=spec['threshold'])&wet


class DailyAccumulator:
    """분모 0 제외 후 날짜→지점 평균을 빠르게 계산. 전체 지점 수는 고정."""
    def __init__(self,frame,common_valid):
        validate(frame);self.frame=frame;self.valid=np.asarray(common_valid,bool)&frame.ice.isin([0,1]).to_numpy()
        self.y=frame.ice.to_numpy(float);self.day,self.keys=pd.factorize(pd.MultiIndex.from_arrays([frame.station,frame.time.dt.normalize()]),sort=True)
        self.n=len(self.keys);self.count=np.bincount(self.day,weights=self.valid,minlength=self.n)
        self.positives=np.bincount(self.day,weights=self.valid&(self.y==1),minlength=self.n)
        self.stations=sorted(frame.station.unique());self.day_station=np.array([self.stations.index(s) for s in self.keys.get_level_values(0)])
        dates=self.keys.get_level_values(1);self.day_winter=np.where(dates<pd.Timestamp('2025-03-01'),2024,2025)
    def compute(self,prediction):
        p=np.asarray(prediction,bool)
        if p.shape!=self.y.shape:raise ValueError('Unaligned prediction')
        tp=np.bincount(self.day,weights=self.valid&(self.y==1)&p,minlength=self.n)
        fp=np.bincount(self.day,weights=self.valid&(self.y==0)&p,minlength=self.n);fn=self.positives-tp
        denominator=2*tp+fp+fn;active=(self.count>=144)&(denominator>0)
        value=np.divide(2*tp,denominator,out=np.zeros_like(tp),where=active)
        means=[]
        for period in ['all',2024,2025]:
            mask=np.ones(self.n,bool) if period=='all' else self.day_winter==period
            sums=np.bincount(self.day_station,weights=np.where(mask,value,0),minlength=len(self.stations))
            counts=np.bincount(self.day_station,weights=active&mask,minlength=len(self.stations))
            means.append(np.divide(sums,counts,out=np.zeros_like(sums),where=counts>0))
        return np.stack(means),dict(tp=int(tp.sum()),fp=int(fp.sum()),fn=int(fn.sum()))
