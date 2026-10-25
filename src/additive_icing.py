"""기온 기준선의 경보를 유지하는 추가 탐지와 지역 내부 후보 선택."""
import numpy as np
import pandas as pd


def additive_prediction(air, score, threshold, cap, available):
    a, s, valid = np.asarray(air, float), np.asarray(score, float), np.asarray(available, bool)
    if a.ndim != 1 or a.shape != s.shape or a.shape != valid.shape or not 0 <= threshold <= 1 or not 0 < cap <= 4:
        raise ValueError('Invalid aligned policy inputs')
    if not np.isfinite(s).all() or not ((s >= 0) & (s <= 1)).all() or not np.isfinite(a[valid]).all():
        raise ValueError('Invalid probability or available temperature')
    return np.where(valid, (a <= 0) | ((a > 0) & (a <= cap) & (s >= threshold)), np.nan)


def candidates(plan):
    rows = [dict(candidate='asos_zero', model=None, threshold=1., cap=0., complexity=0)]
    for model in plan['models']:
        for cap in plan['air_caps_c']:
            for threshold in plan['score_thresholds']:
                rows.append(dict(candidate=f'{model}_cap{cap:g}_p{threshold:g}',model=model,threshold=threshold,cap=cap,complexity=1))
    return rows


def prediction_matrix(frame, scores, policies):
    base = np.where(frame.available, frame.asos_air_temp.le(0), np.nan)
    return np.column_stack([base if p['model'] is None else additive_prediction(frame.asos_air_temp, scores[p['model']], p['threshold'], p['cap'], frame.available) for p in policies])


def metric_table(frame, predictions, policies):
    """완전 날짜별 지표를 지점별 평균한다. 혼동행렬은 전체 유효 행을 센다."""
    matrix = np.asarray(predictions, float)
    if matrix.shape != (len(frame), len(policies)) or not np.isin(matrix[np.isfinite(matrix)], [0,1]).all():
        raise ValueError('Aligned binary policies required')
    if not np.array_equal(np.isfinite(matrix), np.broadcast_to(frame.available.to_numpy(bool)[:,None], matrix.shape)):
        raise ValueError('Common availability changed')
    mask = frame.available.to_numpy(bool) & frame.ice.isin([0,1]).to_numpy()
    f = frame.loc[mask]; y = f.ice.to_numpy(int); matrix = matrix[mask]
    pop = sorted(frame.station.unique()); day, keys = pd.factorize(pd.MultiIndex.from_arrays([f.station, f.time.dt.normalize()]), sort=True)
    n = np.bincount(day); pos = np.bincount(day, weights=y); sites = np.array(keys.get_level_values(0))
    years = np.array([d.year if d.month >= 11 else d.year-1 for d in keys.get_level_values(1)])
    rows = []
    for policy, pred in zip(policies, matrix.T):
        tp = np.bincount(day, weights=y*pred); fp = np.bincount(day, weights=(1-y)*pred); fn = pos-tp
        d = pd.DataFrame({'station':sites,'year':years})
        for name, num, den in [('f1',2*tp,2*tp+fp+fn),('precision',tp,tp+fp),('recall',tp,tp+fn)]:
            d[name] = np.divide(num,den,out=np.full(len(n),np.nan),where=(n==144)&(den>0))
        station = d.groupby('station')[['f1','precision','recall']].mean().reindex(pop)
        r = dict(**policy, f1=float(station.f1.fillna(0).mean()),precision=float(station.precision.mean()),recall=float(station.recall.mean()),
            tp=int(tp.sum()),fp=int(fp.sum()),fn=int(fn.sum()))
        for year in [2024,2025]:
            r[f'f1_{year}']=float(d.loc[d.year.eq(year)].groupby('station').f1.mean().reindex(pop).fillna(0).mean())
        for site, value in station.f1.fillna(0).items():r['site_'+site]=float(value)
        rows.append(r)
    return pd.DataFrame(rows)


def select_policy(table, guarded):
    base = table.loc[table.candidate.eq('asos_zero')].iloc[0]
    eligible = table
    if guarded:
        mask = table.f1.ge(1.01*base.f1) & table.f1.gt(base.f1) & table.precision.ge(base.precision)
        for name in ['f1_2024','f1_2025',*[x for x in table if x.startswith('site_')]]:
            mask &= table[name].ge(base[name])
        eligible = table.loc[mask]
        if eligible.empty:return base.candidate
    return eligible.sort_values(['f1','complexity','cap','threshold','candidate'],ascending=[False,True,True,False,True],kind='stable').iloc[0].candidate
