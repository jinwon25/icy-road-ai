"""보호 관측 없이 두 겨울 회귀 계열과 과거 기상 표현을 대조한다."""
import numpy as np
import pandas as pd
from src.two_winter import validate
from src.submission_runtime import FEATURES
from src.weather_memory_temperature_stable import weather_history


def feature_table(frame,kind='weather'):
    validate(frame)
    if not frame.index.is_unique:raise ValueError('Unique row index required')
    x=frame[list(FEATURES)].astype(float).copy()
    if np.isinf(x.to_numpy()).any():raise ValueError('Infinite inputs')
    if kind=='history':
        parts=[]
        for year,part in frame.groupby('winter'):
            shifted=part.copy()
            if year==2025:shifted['time']=shifted.time-pd.DateOffset(years=1)
            parts.append(weather_history(shifted))
        x=pd.concat([x,pd.concat(parts).reindex(frame.index)],axis=1)
    elif kind=='derived':
        x['air_aws_gap']=x.asos_air_temp-x.aws_air_temp
        x['dewpoint_depression']=x.aws_air_temp-x.aws_dewpoint
        x['humidity_deficit']=100-x.aws_humidity
        x['wind_sqrt']=np.sqrt(x.aws_wind_speed.clip(lower=0))
        x['air_wind_product']=x.asos_air_temp*x.wind_sqrt
        x['hour_second_sin']=2*x.hour_sin*x.hour_cos
        x['hour_second_cos']=x.hour_cos**2-x.hour_sin**2
        for a in ['hour_sin','hour_cos']:
            for b in ['season_sin','season_cos']:x[a+'_'+b]=x[a]*x[b]
    elif kind!='weather':raise ValueError('Unknown feature set')
    return x


def estimator(spec,seed=20261024,threads=2):
    family=spec['family'];n=spec['iterations']
    if family=='hgb':
        from sklearn.ensemble import HistGradientBoostingRegressor
        return HistGradientBoostingRegressor(loss=spec['loss'],learning_rate=.05,max_iter=n,
            max_leaf_nodes=spec['leaves'],min_samples_leaf=100,l2_regularization=10.,early_stopping=False,random_state=seed)
    if family=='catboost':
        from catboost import CatBoostRegressor
        return CatBoostRegressor(loss_function=spec['loss'],iterations=n,depth=spec['depth'],learning_rate=.05,
            l2_leaf_reg=20.,random_seed=seed,thread_count=threads,allow_writing_files=False,verbose=False,nan_mode='Min',boosting_type='Plain')
    if family=='lightgbm':
        from lightgbm import LGBMRegressor
        return LGBMRegressor(objective=spec['loss'],n_estimators=n,num_leaves=spec['leaves'],learning_rate=.05,
            min_child_samples=100,reg_lambda=10.,random_state=seed,n_jobs=threads,verbosity=-1,deterministic=True,force_col_wise=True)
    if family=='xgboost':
        from xgboost import XGBRegressor
        extra={'huber_slope':1.5} if spec['loss']=='reg:pseudohubererror' else {}
        return XGBRegressor(objective=spec['loss'],n_estimators=n,max_depth=spec['depth'],learning_rate=.05,
            min_child_weight=100,reg_lambda=20.,random_state=seed,n_jobs=threads,tree_method='hist',device='cpu',verbosity=0,**extra)
    raise ValueError('Unknown estimator')


def weights(frame,spec):
    if not spec.get('group_balance'):return None
    # 원 대회 14곳을 한 지역 집합으로, 외부의 나머지 그룹을 각각 같은 총 비중으로 둔다.
    counts=frame.group.value_counts()
    return frame.group.map(len(frame)/(len(counts)*counts)).to_numpy(float)


def temperature_gate(frame,prediction,baseline,plan):
    from src.temperature_transfer import regression_report
    new=regression_report(frame,prediction);old=regression_report(frame,baseline)
    if new['pooled']['n']!=old['pooled']['n']:raise ValueError('Changed valid-row denominator')
    p=np.asarray(prediction,float);b=np.asarray(baseline,float)
    if not np.array_equal(np.isfinite(p),np.isfinite(b)):raise ValueError('Mismatched missing predictions')
    winter={}
    for year in [2024,2025]:
        mask=frame.winter.eq(year).to_numpy();f=frame.loc[mask]
        winter[str(year)]={'new':regression_report(f,p[mask]),'baseline':regression_report(f,b[mask])}
    regions={}
    for group in sorted(frame.group.unique()):
        mask=frame.group.eq(group).to_numpy();f=frame.loc[mask]
        regions[group]={'new':regression_report(f,p[mask])['pooled'],'baseline':regression_report(f,b[mask])['pooled']}
    gates=dict(pooled_improves=new['pooled']['mae']<=(1-plan['pooled_improvement_min'])*old['pooled']['mae'],
        station_macro_improves=new['station_macro']['mae']<old['station_macro']['mae'],
        each_winter=all(v['new']['pooled']['mae']<=(1+plan['each_winter_max_harm'])*v['baseline']['pooled']['mae'] for v in winter.values()),
        each_station=all(new['stations'][s]['mae']<=(1+plan['each_station_max_harm'])*old['stations'][s]['mae'] for s in old['stations']),
        cold_noninferior=new['near_freezing']['mae']<=(1+plan['near_freezing_max_harm'])*old['near_freezing']['mae'],
        regional_support=sum(v['new']['mae']<=v['baseline']['mae'] for v in regions.values())>=plan['minimum_noninferior_regions'])
    return dict(regression=new,winters=winter,regions=regions,gates=gates,eligible=all(gates.values()))
