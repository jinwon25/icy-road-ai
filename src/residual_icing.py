"""기온 시작값을 학습한 모델의 잔차만 제한적으로 결합한다."""
import numpy as np


def prior_margin(air, kind):
    a=np.asarray(air,dtype=np.float32)
    if a.ndim!=1 or np.isinf(a).any():raise ValueError('Invalid temperatures')
    if kind=='zero':return np.zeros(len(a),np.float32)
    if kind!='temperature':raise ValueError('Unknown prior')
    return -np.nan_to_num(a,nan=0.)/2


def residual_prediction(air, full_margin, prior, cap, direction, available):
    a=np.asarray(air,float);m=np.asarray(full_margin,float);b=np.asarray(prior,float);v=np.asarray(available,bool)
    if a.ndim!=1 or any(x.shape!=a.shape for x in [m,b,v]) or not 0<cap<=2:raise ValueError('Invalid aligned inputs')
    if not np.isfinite(m).all() or not np.isfinite(b).all() or not np.isfinite(a[v]).all():raise ValueError('Invalid finite inputs')
    correction=np.clip(2*(m-b),-cap,cap)
    if direction=='reject_only':correction=np.minimum(correction,0)
    elif direction!='symmetric':raise ValueError('Unknown direction')
    return np.where(v,a<=correction,np.nan)


def policies(plan):
    result=[dict(candidate='asos_zero',model=None,rounds=0,cap=0.,direction='baseline',complexity=0)]
    for model in plan['models']:
        for rounds in plan['rounds']:
            for cap in plan['caps_c']:
                for direction in plan['directions']:
                    result.append(dict(candidate=f'{model["name"]}_r{rounds}_{direction}_c{cap:g}',model=model['name'],rounds=rounds,cap=cap,direction=direction,complexity=1))
    return result


def predictions(frame, specs, model_specs):
    priors={m['name']:prior_margin(frame.asos_air_temp,m['prior']) for m in model_specs}
    base=np.where(frame.available,frame.asos_air_temp.le(0),np.nan)
    return np.column_stack([base if p['model'] is None else residual_prediction(frame.asos_air_temp,
        frame[p['model']+'_r'+str(p['rounds'])],priors[p['model']],p['cap'],p['direction'],frame.available) for p in specs])


def select(table,guarded):
    eligible=table
    if guarded:
        base=table.loc[table.candidate.eq('asos_zero')].iloc[0]
        mask=table.f1.ge(1.01*base.f1)&table.f1.gt(base.f1)
        for col in ['precision','recall','f1_2024','f1_2025',*[c for c in table if c.startswith('site_')]]:mask &= table[col].ge(base[col])
        eligible=table.loc[mask]
        if eligible.empty:return 'asos_zero'
    return eligible.sort_values(['f1','complexity','cap','rounds','candidate'],ascending=[False,True,True,True,True],kind='stable').iloc[0].candidate
