"""과거 창 전량·48저장모형 추론·대표 재학습·집계·분할·봉인을 검산한다."""
import argparse
import gc
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from src.development_resampling import circular_day_indices
from scripts.evaluate_objective_icing import read,write,verify_preserved
from scripts.audit_road_weather_transfer import compare,measure


def independent_history(f, base):
    """rollingを使用せず二分探索と累積和から同じ過去窓を計算する。"""
    output = base.copy(); fields = ['asos_air_temp','asos_ground_temp','asos_humidity',
        'asos_wind_speed','asos_solar_mj_m2','aws_air_temp','aws_humidity','aws_wind_speed']
    for hours in [3,24]:
        for field in fields:
            for kind in ['mean','departure','coverage']:
                output[f'{field}_{kind}_{hours}h'] = np.nan
    for _, q in f.groupby(['station','winter']):
        idx = q.sort_values('time').index.to_numpy()
        times = f.loc[idx,'time'].to_numpy(dtype='datetime64[ns]').astype(np.int64)
        values = base.loc[idx,fields].to_numpy(float); good = np.isfinite(values)
        sums = np.vstack([np.zeros(len(fields)),np.cumsum(np.where(good,values,0),axis=0)])
        counts = np.vstack([np.zeros(len(fields)),np.cumsum(good,axis=0)])
        right = np.arange(len(idx))+1
        for hours, minimum in [(3,6),(24,48)]:
            left = np.searchsorted(times,times-int(hours*3600e9),side='right')
            n = counts[right]-counts[left]; total = sums[right]-sums[left]
            mean = np.divide(total,n,out=np.full_like(total,np.nan),where=n>=minimum)
            for j,field in enumerate(fields):
                output.loc[idx,f'{field}_mean_{hours}h'] = mean[:,j]
                output.loc[idx,f'{field}_departure_{hours}h'] = values[:,j]-mean[:,j]
                output.loc[idx,f'{field}_coverage_{hours}h'] = n[:,j]/(hours*6)
    return output


def numbers(f,column):
    return dict(pooled=measure(f,column),
        directions={str(k):measure(q,column) for k,q in f.groupby('winter')},
        regions={str(k):measure(q,column) for k,q in f.groupby('group')},
        cold=measure(f.loc[f.cold_input],column))


def bootstrap(f,candidate,reference,settings):
    total = np.zeros((settings['repetitions'],2))
    for year in [2024,2025]:
        q = f.loc[f.winter.eq(year)]
        offsets = ((q.time.dt.normalize()-pd.Timestamp(year,11,1))/pd.Timedelta(days=1)).to_numpy(int)
        delta = np.abs(q[candidate].to_numpy()-q.observed.to_numpy())-np.abs(q[reference].to_numpy()-q.observed.to_numpy())
        sums = np.bincount(offsets,weights=delta,minlength=120)
        counts = np.bincount(offsets,minlength=120)
        idx = circular_day_indices(120,settings['block_days'],settings['repetitions'],settings['seed']+year-2024)
        total[:,0] += sums[idx].sum(axis=1); total[:,1] += counts[idx].sum(axis=1)
    delta = total[:,0]/total[:,1]
    return dict(quantiles=np.quantile(delta,[.025,.5,.975]).tolist(),
        fraction_improved=float((delta<0).mean()),repetitions=len(delta),
        interpretation='fixed_development_date_sensitivity_not_new_population_confidence')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'config/weather_temporal_20261101.json')
    args=parser.parse_args();plan=read(args.config);out=ROOT/plan['output']
    summary=read(out/'summary.json');recorded=read(out/'plan.json')
    if (out/'independent_verification.json').exists():raise FileExistsError('Preserve completed audit')
    # 완료 직전 생산 실행이 확인한 봉인을 기준으로 하며, 이 감사의 끝에서 다시 전량 해시 검사한다.
    frozen=summary['preservation'];assert frozen==recorded['preservation']
    for relative,digest in recorded['signatures'].items():assert sha(ROOT/relative)==digest,relative
    for relative,digest in summary['files'].items():assert sha(out/relative)==digest,relative
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations'])
    assert set(f.winter)=={2024,2025} and f.station.nunique()==23
    base=pd.read_parquet(out/'instant_residual_features.parquet')
    # 원 특징 구성과 별도로 시각 제한과 허용 열을 확인한다.
    for prefix,maximum,fields in [('asos',60,['air_temp','ground_temp','humidity','rain_mm','snow_cm',
        'cloud_tenths','solar_mj_m2','wind_speed','dewpoint_obs','pressure','visibility','new_snow3h','soil5cm']),
        ('aws',15,['air_temp','humidity','wind_speed','rain_15m','dewpoint'])]:
        good=(f[prefix+'_age_minutes']>0)&(f[prefix+'_age_minutes']<=maximum)
        for field in fields:
            np.testing.assert_allclose(base[prefix+'_'+field],f[prefix+'_'+field].where(good),atol=0,rtol=0,equal_nan=True)
    assert len(base.columns)==34 and not {'station','winter','air_temperature','relative_humidity','wind_speed','ice','road_temp'}&set(base)
    for column in ['asos_age_minutes','aws_age_minutes','hour_sin','hour_cos','season_sin',
        'season_cos','asos_distance_km','aws_distance_km','solar_altitude_deg','solar_sine_positive']:
        np.testing.assert_array_equal(base[column],f[column])
    for target,field in zip(['air_temperature','relative_humidity','wind_speed'],['air_temp','humidity','wind_speed']):
        np.testing.assert_array_equal(base['aws_asos_'+target+'_contrast'],base['aws_'+field]-base['asos_'+field])
    np.testing.assert_array_equal(base.asos_ground_air_contrast,base.asos_ground_temp-base.asos_air_temp)
    np.testing.assert_array_equal(base.asos_dewpoint_gap,base.asos_air_temp-base.asos_dewpoint_obs)
    np.testing.assert_array_equal(base.aws_dewpoint_gap,base.aws_air_temp-base.aws_dewpoint)
    history=pd.read_parquet(out/'history_residual_features.parquet')
    independent=independent_history(f,base)
    pd.testing.assert_frame_equal(history,independent,atol=2e-8,rtol=1e-9,check_exact=False)
    print('FEATURES',history.size,flush=True)
    feature_values=history.size
    del independent,history,base
    gc.collect();pa.default_memory_pool().release_unused()
    prediction_values=0;metric_checks=0;refits=[]
    fields={'air_temperature':'air_temp','relative_humidity':'humidity','wind_speed':'wind_speed'}
    for target in plan['targets']:
        field=fields[target];asos=f['asos_'+field].where((f.asos_age_minutes>0)&(f.asos_age_minutes<=60)).to_numpy()
        aws=f['aws_'+field].where((f.aws_age_minutes>0)&(f.aws_age_minutes<=15)).to_numpy()
        nearest=np.where(np.isfinite(aws),aws,asos)
        valid=np.isfinite(f[target])&np.isfinite(asos)&np.isfinite(nearest)
        p=pd.read_parquet(out/target/'predictions.parquet')
        index=pd.MultiIndex.from_frame(f[['station','time']]);idx=index.get_indexer(pd.MultiIndex.from_frame(p[['station','time']]))
        assert (idx>=0).all() and len(set(idx))==len(idx)
        np.testing.assert_array_equal(np.sort(idx),np.flatnonzero(valid&f.group.ne('competition')))
        np.testing.assert_array_equal(p.observed,f.loc[idx,target])
        np.testing.assert_array_equal(p.asos,asos[idx]);np.testing.assert_array_equal(p.aws_fallback,nearest[idx])
        np.testing.assert_array_equal(p.cold_input,np.abs(f.loc[idx,'asos_air_temp'])<=3)
        for spec in [r for r in summary['fits'] if r['target']==target]:
            candidate=spec['candidate'];held=spec['held'];year=spec['query_winter']
            train=valid&f.group.ne(held)&f.winter.ne(year);query=valid&f.group.eq(held)&f.winter.eq(year)
            assert spec['training_rows']==int(train.sum()) and spec['query_rows']==int(query.sum())
            assert spec['training_stations']==sorted(f.loc[train,'station'].unique())
            assert spec['training_winters']==[2025 if year==2024 else 2024]
            assert not set(f.loc[train,'station'])&set(f.loc[query,'station'])
            assert spec['query_stations']==sorted(f.loc[query,'station'].unique())
            assert not set(f.loc[train,'station'])&set(plan['blocked_stations'])
            stem=f'{candidate}_{held}_{year}';model=joblib.load(out/target/(stem+'.joblib'))
            x=pd.read_parquet(out/(candidate+'_features.parquet'))
            assert list(model.feature_names_in_)==list(x)==spec['features']
            assert all(model.get_params()[key]==value for key,value in plan['model'].items())
            query_x=x.loc[query]
            refitting=held=='honam_baekyang' and year==2025
            if refitting:train_x=x.loc[train]
            del x;gc.collect();pa.default_memory_pool().release_unused()
            with deny_network() as attempts,threadpool_limits(limits=2):raw=model.predict(query_x)+nearest[query]
            assert not attempts
            predicted=np.clip(raw,0,100) if target=='relative_humidity' else np.maximum(raw,0) if target=='wind_speed' else raw
            np.testing.assert_array_equal(predicted,np.load(out/target/(stem+'.npy'),allow_pickle=False))
            saved=p.loc[p.group.eq(held)&p.winter.eq(year),candidate].to_numpy()
            np.testing.assert_array_equal(predicted,saved);prediction_values+=len(predicted)
            if refitting:
                weights=1/f.loc[train].groupby(['station','winter']).station.transform('size').to_numpy(float)
                weights/=weights.mean();refit=HistGradientBoostingRegressor(**plan['model'])
                with deny_network() as attempts,threadpool_limits(limits=2):
                    refit.fit(train_x,f.loc[train,target].to_numpy()-nearest[train],sample_weight=weights)
                    raw_refit=refit.predict(query_x)
                    raw_original=model.predict(query_x)
                assert not attempts;np.testing.assert_array_equal(raw_refit,raw_original)
                refits.append(dict(target=target,candidate=candidate,held=held,query_winter=year,exact=True))
                del refit,train_x
            del model,query_x
            gc.collect();pa.default_memory_pool().release_unused()
            print('AUDIT',target,candidate,year,held,flush=True)
        r=summary['reports'][target]
        for column in ['asos','aws_fallback',*plan['candidates']]:metric_checks+=compare(numbers(p,column),r['metrics'][column])
        for name,candidate,reference in [('history_vs_instant_bootstrap','history_residual','instant_residual'),
            ('instant_vs_aws_bootstrap','instant_residual','aws_fallback')]:
            metric_checks+=compare(bootstrap(p,candidate,reference,plan['bootstrap']),r[name])
        c=r['metrics']['history_residual'];b=r['metrics']['instant_residual'];g=plan['gates']
        gates=dict(pooled=c['pooled']['mae']<=b['pooled']['mae']*(1-g['minimum_mae_reduction_vs_instant']),
            both_directions=all(c['directions'][y]['mae']<=v['mae']*g['maximum_direction_mae_ratio'] for y,v in b['directions'].items()),
            every_region=all(c['regions'][k]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for k,v in b['regions'].items()),
            cold=c['cold']['mae']<=b['cold']['mae']*g['maximum_cold_air_mae_ratio'],
            date_sensitivity=r['history_vs_instant_bootstrap']['quantiles'][2]<0)
        assert gates==r['history_gates'] and all(gates.values())==r['history_success']
    assert len(refits)==6 and len(summary['fits'])==48 and verify_preserved()==frozen
    write(out/'independent_verification.json',dict(status='passed',summary_sha256=sha(out/'summary.json'),
        history_feature_values=feature_values,prediction_values=prediction_values,metric_checks=metric_checks,
        exact_refits=refits,preservation=frozen,audit_script_sha256=sha(Path(__file__))))
    print('VERIFIED',prediction_values,metric_checks,len(refits),flush=True)


if __name__=='__main__':main()
