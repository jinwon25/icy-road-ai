"""최신 지점균등 일별 F1을 근사하는 제한 기온 보정 후보. 입력은 ASOS 기상만 허용."""
import numpy as np
import pandas as pd
from src.anchored_icing import linear_features

HINGES={'asos_air_temp':[-5.,0.,5.],'asos_ground_temp':[-5.,0.,5.],
        'asos_humidity':[80.,95.],'dewpoint_depression':[0.,3.]}

def features(frame):
    x=linear_features(frame)
    for name,knots in HINGES.items():
        for knot in knots:x[name+'_above_'+str(knot)]=(x[name]-knot).clip(lower=0)
    return x

def preprocessing(x):
    a=x.to_numpy(float)
    if np.isinf(a).any():raise ValueError('Infinite weather feature')
    med=np.array([np.median(c[np.isfinite(c)]) if np.isfinite(c).any() else 0. for c in a.T])
    v=np.where(np.isnan(a),med,a);scales=v.std(axis=0);scales[scales<1e-8]=1
    return dict(medians=med,means=v.mean(axis=0),scales=scales)

def transform(x,model):
    a=x.to_numpy(float)
    if np.isinf(a).any():raise ValueError('Infinite weather feature')
    missing=np.isnan(a);z=(np.where(missing,model['medians'],a)-model['means'])/model['scales']
    return np.concatenate([np.clip(z,-8,8),missing.astype(float)],axis=1).astype(np.float32)

def correction(frame,model):
    x=features(frame)
    if list(x)!=list(model['feature_names']):raise ValueError('Weather feature order mismatch')
    z=transform(x,model)
    # NumPy 추론을 실행 계약으로 고정하며 외부 서비스·PyTorch가 필요하지 않다.
    return (float(model['cap'])*np.tanh(z@model['coefficient']+float(model['intercept']))).astype(float)

def fit(frame,settings):
    import torch
    from torch.nn import functional as F
    from src.synoptic_icing import sample_weights
    if frame.empty or frame.duplicated(['station','time']).any() or not frame.ice.isin([0,1]).all():raise ValueError('Unique binary training rows required')
    f=frame.reset_index(drop=True);x=features(f);prep=preprocessing(x)
    full=transform(x,prep);unique,inverse=np.unique(full,axis=0,return_inverse=True)
    z=torch.from_numpy(unique);ix=torch.from_numpy(inverse)
    y=torch.tensor(f.ice.to_numpy(float),dtype=torch.float32)
    air=torch.tensor(f.asos_air_temp.to_numpy(float),dtype=torch.float32)
    if not torch.isfinite(air).all():raise ValueError('Finite ASOS air temperature required')
    day_ids,keys=pd.factorize(pd.MultiIndex.from_arrays([f.station,f.time.dt.normalize()]),sort=True)
    station_ids,station_keys=pd.factorize(pd.Index(f.station),sort=True)
    station_lookup={s:i for i,s in enumerate(station_keys)}
    day_station=torch.tensor([station_lookup[s] for s,_ in keys],dtype=torch.long)
    ids=torch.tensor(day_ids,dtype=torch.long)
    actual=np.bincount(day_ids,weights=f.ice,minlength=len(keys));positive=torch.tensor(actual>0)
    station_eligible=torch.tensor(np.bincount(station_ids,weights=f.ice,minlength=len(station_keys))>0)
    weights=torch.tensor(sample_weights(f,'day'),dtype=torch.float32)
    coefficient=torch.zeros(z.shape[1],requires_grad=True);intercept=torch.zeros((),requires_grad=True)
    optimizer=torch.optim.Adam([coefficient,intercept],lr=settings['learning_rate']);history=[]
    for step in range(settings['steps']):
        optimizer.zero_grad();delta=settings['cap_c']*torch.tanh(z@coefficient+intercept)
        logits=(delta[ix]-air)/2;prob=torch.sigmoid(logits)
        tp=torch.zeros(len(keys)).scatter_add(0,ids,prob*y)
        den=torch.zeros(len(keys)).scatter_add(0,ids,prob+y)
        soft_f1=2*tp/den.clamp_min(1e-8)
        peak=torch.zeros(len(keys)).scatter_reduce(0,ids,prob,reduce='amax',include_self=True)
        numerator=torch.zeros(len(station_keys)).scatter_add(0,day_station,torch.where(positive,soft_f1,0.))
        denominator=torch.zeros(len(station_keys)).scatter_add(0,day_station,torch.where(positive,1.,peak))
        ratio=(1-numerator[station_eligible]/denominator[station_eligible].clamp_min(1e-8)).mean()
        bce=(weights*F.binary_cross_entropy_with_logits(logits,y,reduction='none')).mean()
        loss=.25*bce+.75*ratio+settings['l2']*coefficient.square().sum()
        if not torch.isfinite(loss):raise ValueError('Nonfinite objective')
        loss.backward();optimizer.step()
        if step in (0,settings['steps']-1):history.append(float(loss.detach()))
    return dict(**prep,coefficient=coefficient.detach().numpy(),intercept=intercept.detach().numpy(),cap=np.array(settings['cap_c']),
        feature_names=np.asarray(x.columns,dtype=str),history=np.array(history),unique_training_inputs=np.array(len(unique)))