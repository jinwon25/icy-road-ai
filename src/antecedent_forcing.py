"""기상 대리변수의 감쇠 누적 조건. 실제 노면온도·노면상태는 입력에 넣지 않는다.

Yi & Seo (2026), arXiv:2609.33528 식 (2), (5), (6)를 참고한 자체 구현이다.
1분 노면 관측을 사용하는 원 논문과 달리 엄격한 과거 기상 연결값을 사용한다.
"""
import numpy as np
import pandas as pd
import torch

from src.objective_icing import features as base_features
from src.objective_icing import fit_preprocessor, transform, group_data, data_loss


def frost_point(air, humidity):
    air=np.asarray(air,float);rh=np.asarray(humidity,float)
    if air.shape!=rh.shape:raise ValueError('Aligned temperature and humidity required')
    good=np.isfinite(air)&np.isfinite(rh)&(rh>0)&(rh<=100)&(air>-100)&(air<100)
    result=np.full(air.shape,np.nan)
    value=np.log(rh[good]/100)+17.62*air[good]/(243.12+air[good])
    result[good]=272.62*value/(22.46-value)
    return result


def accumulated_conditions(minutes, temperature, frost, tau_minutes, max_gap_minutes=15):
    """상수 입력의 정확한 구간 적분과 부호 전환을 계산한다. 공백에는 감쇠만 한다.

    온도 누적값은 tau로 나누어 °C 척도로 반환한다. 첫 시각의 누적은 0이다.
    0°C 관측은 부호를 바꾸지 않으며 결측·15분 초과 공백은 직전 부호를 지운다.
    """
    t=np.asarray(minutes,float);temp=np.asarray(temperature,float);fp=np.asarray(frost,float)
    if t.ndim!=1 or t.shape!=temp.shape or t.shape!=fp.shape or not np.isfinite(t).all():
        raise ValueError('Aligned one-dimensional series required')
    if np.any(np.diff(t)<=0) or tau_minutes<=0 or max_gap_minutes<=0:
        raise ValueError('Increasing time and positive scales required')
    result=np.full((len(t),4),np.nan);cold=deposition=cycles=age=0.;last_sign=0
    for i in range(len(t)):
        dt=0. if i==0 else t[i]-t[i-1]
        decay=np.exp(-dt/tau_minutes);cold*=decay;deposition*=decay;cycles*=decay
        continuous=i>0 and dt<=max_gap_minutes
        if not continuous:last_sign=0;age=0.
        if np.isfinite(temp[i]):
            increment=tau_minutes*(-np.expm1(-dt/tau_minutes)) if continuous else 0.
            cold+=max(0.,-temp[i])*increment
            if np.isfinite(fp[i]):deposition+=max(0.,fp[i]-temp[i])*increment
            current_sign=int(np.sign(temp[i]))
            if current_sign:
                if continuous and last_sign and current_sign!=last_sign:cycles+=1
                # 긴 공백의 첫 관측에서는 부호를 재설정하지 않는다.
                last_sign=current_sign if continuous or i==0 else 0
            age=age+dt if continuous and i>0 and np.isfinite(temp[i-1]) else 0.
            result[i]=[cold/tau_minutes,deposition/tau_minutes if np.isfinite(fp[i]) else np.nan,cycles,min(age,360.)/360.]
        else:
            last_sign=0;age=0.
    return result


def local_features(frame):
    """현재 기상 대리변수와 감쇠 이력을 같은 행에 연결한다. 이력은 전체 순서에서 계산한다."""
    if frame.duplicated(['station','time']).any():raise ValueError('Unique station timestamps required')
    if not frame.index.equals(pd.RangeIndex(len(frame))):raise ValueError('Reset source index before feature construction')
    x=base_features(frame)
    local_good=frame.aws_age_minutes.between(0,15,inclusive='right')
    for c in ['aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint']:
        x[c]=frame[c].where(local_good)
    x['aws_source_age_minutes']=frame.aws_age_minutes
    fp_asos=frost_point(frame.asos_air_temp,frame.asos_humidity)
    fp_aws=frost_point(x.aws_air_temp,x.aws_humidity)
    x['asos_frost_point']=fp_asos;x['aws_frost_point']=fp_aws
    x['asos_ground_frost_margin']=frame.asos_ground_temp-fp_asos
    x['aws_air_frost_margin']=x.aws_air_temp-fp_aws
    x['aws_asos_air_contrast']=x.aws_air_temp-frame.asos_air_temp
    for name in ['0_to_7cm','7_to_28cm']:
        x['era5_soil_air_contrast_'+name]=frame['era5_soil_temperature_'+name]-frame.era5_temperature_2m
    x['era5_snow_depth']=frame.era5_snow_depth
    x['era5_soil_moisture_0_to_7cm']=frame.era5_soil_moisture_0_to_7cm
    instantaneous=list(x)
    for source,temp,frost in [('asos_air',frame.asos_air_temp.to_numpy(),fp_asos),
                              ('asos_ground',frame.asos_ground_temp.to_numpy(),fp_asos),
                              ('aws_air',x.aws_air_temp.to_numpy(),fp_aws)]:
        for tau in [30,360]:
            for name in ['cold','deposition','freeze_thaw']:
                x[f'{source}_{name}_{tau}m']=np.nan
        x[source+'_history_fraction6h']=np.nan;x[source+'_change1h']=np.nan
        for _,part in frame.groupby(['station','winter'],sort=True):
            order=part.sort_values('time').index.to_numpy();times=frame.loc[order,'time']
            minutes=times.to_numpy(dtype='datetime64[ns]').astype(np.int64)/60e9
            for tau in [30,360]:
                values=accumulated_conditions(minutes,temp[order],frost[order],tau)
                for j,name in enumerate(['cold','deposition','freeze_thaw']):x.loc[order,f'{source}_{name}_{tau}m']=values[:,j]
            x.loc[order,source+'_history_fraction6h']=values[:,3]
            series=pd.Series(temp[order],index=pd.DatetimeIndex(times))
            past=series.reindex(series.index-pd.Timedelta(hours=1)).to_numpy()
            x.loc[order,source+'_change1h']=series.to_numpy()-past
    if np.isinf(x.to_numpy(float)).any():raise ValueError('Infinite forcing feature')
    return x,instantaneous


def fit_forcing(frame, x, settings):
    """기존 BCE·보정 한계·학습 횟수를 유지하고 입력만 교체한다."""
    preprocessing=fit_preprocessor(x);z=torch.from_numpy(transform(x,preprocessing))
    y=torch.tensor(frame.ice.to_numpy(),dtype=torch.float32)
    air=torch.tensor(frame.asos_air_temp.to_numpy(),dtype=torch.float32)
    if not torch.isfinite(air).all():raise ValueError('Finite baseline air required')
    grouped={key:torch.tensor(value,dtype=torch.long if key.endswith('_ids') else torch.float32)
             for key,value in group_data(frame).items()}
    coefficient=torch.zeros(z.shape[1],requires_grad=True);intercept=torch.zeros((),requires_grad=True)
    optimizer=torch.optim.Adam([coefficient,intercept],lr=settings['learning_rate']);history=[]
    for step in range(settings['steps']):
        optimizer.zero_grad();delta=settings['cap_c']*torch.tanh(z@coefficient+intercept)
        loss=data_loss((delta-air)/2,y,grouped,'bce_day')+settings['l2']*coefficient.square().sum()
        if not torch.isfinite(loss):raise ValueError('Nonfinite loss')
        loss.backward();optimizer.step()
        if step in [0,settings['steps']-1]:history.append(float(loss.detach()))
    return dict(**preprocessing,coefficient=coefficient.detach().numpy(),intercept=intercept.detach().numpy(),
        cap=np.array(settings['cap_c']),feature_names=np.asarray(x.columns,dtype=str),history=np.array(history))


def correction_from_features(x,model):
    if list(x)!=list(model['feature_names']):raise ValueError('Feature order mismatch')
    z=transform(x,model)
    with torch.no_grad():
        result=float(model['cap'])*torch.tanh(torch.from_numpy(z)@torch.from_numpy(model['coefficient'])+float(model['intercept']))
    return result.numpy().astype(float)
