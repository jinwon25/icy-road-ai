"""독립 창 합산의 전량 동치·문맥 불변·12추론·4재학습·지표·봉인을 검산한다."""
import gc
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved
from scripts.finalize_weather_history_stable_20261101 import verify_training_sources
from scripts.audit_weather_history_spatial_20261101 import report
from scripts.audit_weather_temporal import bootstrap
from scripts.audit_road_weather_transfer import compare
from src.weather_history_stable import stable_temporal_features
from src.weather_temporal import HISTORY_FIELDS
from src.road_weather_runtime import INPUT_COLUMNS
from src.offline_runtime import deny_network
from src.data_source import sha256_file as sha


def main():
    plan=read(ROOT/'config/weather_humidity_stable_20261101.json');out=ROOT/plan['output'];old=ROOT/plan['old_temporal']
    summary=read(out/'summary.json');recorded=read(out/'plan.json')
    if (out/'independent_verification.json').exists():raise FileExistsError('Preserve completed stable audit')
    assert verify_training_sources(out)==summary['fit_counter_fix']
    for path,digest in summary['files'].items():assert sha(out/path)==digest,path
    prior=read(old/'summary.json');audit=read(old/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(old/'summary.json')
    for name in ['instant_residual_features.parquet','history_residual_features.parquet']:
        assert sha(old/name)==prior['files'][name]
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations']) and not {'ice','road_temp','state_raw'}&set(f)
    columns=list(pd.read_parquet(old/'instant_residual_features.parquet',columns=[]).columns)
    import pyarrow.parquet as pq
    base_columns=pq.ParquetFile(old/'instant_residual_features.parquet').schema.names
    checked=0;maximum=0.
    for columns,reference,exact in [(base_columns,'instant_residual_features.parquet',True),
        *[([f'{field}_{kind}_{hours}h' for field in HISTORY_FIELDS for kind in ['mean','departure','coverage']],
            'history_residual_features.parquet',False) for hours in [3,24]]]:
        a=pd.read_parquet(old/reference,columns=columns);b=pd.read_parquet(out/'features.parquet',columns=columns)
        pd.testing.assert_frame_equal(a,b,check_exact=exact,atol=2e-8,rtol=1e-9)
        maximum=max(maximum,float(np.nanmax(np.abs(a.to_numpy()-b.to_numpy()))));checked+=a.size
        del a,b;gc.collect();pa.default_memory_pool().release_unused()
    all_x=pd.read_parquet(out/'features.parquet');prefix_values=0
    for station in ['12207','23205','33205','33207']:
        for year in [2024,2025]:
            for day in [pd.Timestamp(year,12,15),pd.Timestamp(year+1,1,15)]:
                q=f.loc[f.station.eq(station)&f.time.ge(day-pd.Timedelta(days=1))&f.time.lt(day+pd.Timedelta(days=1))]
                _,local=stable_temporal_features(q[['station','time','winter',*INPUT_COLUMNS]].reset_index(drop=True))
                keep=q.time.ge(day).to_numpy()
                expected=all_x.loc[q.index[keep]].reset_index(drop=True)
                pd.testing.assert_frame_equal(local.loc[keep].reset_index(drop=True),expected,check_exact=True)
                prefix_values+=expected.size
    del all_x;gc.collect();pa.default_memory_pool().release_unused()
    print('FEATURES',checked,'prefix exact',prefix_values,flush=True)
    asos=f.asos_humidity.where((f.asos_age_minutes>0)&(f.asos_age_minutes<=60)).to_numpy()
    aws=f.aws_humidity.where((f.aws_age_minutes>0)&(f.aws_age_minutes<=15)).to_numpy()
    nearest=np.where(np.isfinite(aws),aws,asos)
    good=np.isfinite(f.relative_humidity)&np.isfinite(asos)&np.isfinite(nearest)
    refits=[];pred_values=0;metric_checks=0
    for mode in ['joint','spatial']:
        p=pd.read_parquet(out/mode/'predictions.parquet')
        idx=pd.MultiIndex.from_frame(f[['station','time']]).get_indexer(pd.MultiIndex.from_frame(p[['station','time']]))
        assert (idx>=0).all() and len(set(idx))==len(idx)
        np.testing.assert_array_equal(np.sort(idx),np.flatnonzero(good&f.group.ne('competition')))
        for column,values in [('observed',f.relative_humidity.to_numpy()),('asos',asos),('aws_fallback',nearest)]:
            np.testing.assert_array_equal(p[column],values[idx])
        np.testing.assert_array_equal(p.cold_input,np.abs(f.loc[idx,'asos_air_temp'])<=3)
        for spec in [r for r in summary['fits'] if r['mode']==mode]:
            held=spec['held'];year=spec['query_winter'];stem=held+('_'+str(year) if year is not None else '')
            train=good&f.group.ne(held);query=good&f.group.eq(held)
            select=p.group.eq(held)
            if mode=='joint':train&=f.winter.ne(year);query&=f.winter.eq(year);select&=p.winter.eq(year)
            assert spec['training_rows']==int(train.sum()) and spec['query_rows']==int(query.sum())
            assert spec['training_stations']==sorted(f.loc[train,'station'].unique())
            assert spec['training_winters']==sorted(int(y) for y in f.loc[train,'winter'].unique())
            assert not set(f.loc[train,'station'])&set(f.loc[query,'station'])
            if mode=='joint':assert not set(f.loc[train,'winter'])&set(f.loc[query,'winter'])
            reference=ROOT/spec['reference_model'];assert sha(reference)==spec['reference_model_sha256']
            np.testing.assert_array_equal(p.loc[select,'instant_residual'],np.load(reference.with_suffix('.npy'),allow_pickle=False))
            x=pd.read_parquet(out/'features.parquet');query_x=x.loc[query]
            refitting=(mode=='joint' and held=='honam_baekyang') or (mode=='spatial' and held in ['honam_baekyang','seohaean_seocheon'])
            if refitting:train_x=x.loc[train]
            del x;gc.collect();pa.default_memory_pool().release_unused()
            model=joblib.load(out/mode/(stem+'.joblib'))
            assert all(model.get_params()[k]==v for k,v in plan['model'].items())
            assert list(model.feature_names_in_)==list(query_x)==spec['features']
            with deny_network() as attempts,threadpool_limits(limits=2):actual=np.clip(model.predict(query_x)+nearest[query],0,100)
            assert not attempts
            np.testing.assert_array_equal(actual,p.loc[select,'stable_history'])
            np.testing.assert_array_equal(actual,np.load(out/mode/(stem+'.npy'),allow_pickle=False));pred_values+=2*len(actual)
            if refitting:
                counts=f.loc[train].groupby(['station','winter']).station.transform('size').to_numpy(float)
                weights=1/counts;weights/=weights.mean()
                replay=HistGradientBoostingRegressor(**plan['model'])
                with deny_network() as attempts,threadpool_limits(limits=2):
                    replay.fit(train_x,f.loc[train,'relative_humidity'].to_numpy()-nearest[train],sample_weight=weights)
                    values=np.clip(replay.predict(query_x)+nearest[query],0,100)
                assert not attempts;np.testing.assert_array_equal(values,actual)
                refits.append(dict(mode=mode,held=held,query_winter=year));del replay,train_x
            del model,query_x;gc.collect();pa.default_memory_pool().release_unused()
            print('AUDIT',mode,held,year,flush=True)
        result=summary['reports'][mode]
        for column in ['asos','aws_fallback','instant_residual','stable_history']:
            metric_checks+=compare(report(p,column),result['metrics'][column])
        metric_checks+=compare(bootstrap(p,'stable_history','instant_residual',plan['bootstrap']),result['bootstrap'])
        c=result['metrics']['stable_history'];b=result['metrics']['instant_residual'];g=plan['gates']
        gates=dict(pooled=c['pooled']['mae']<=b['pooled']['mae']*(1-g['minimum_mae_reduction']),
            both_winters=all(c['winters'][y]['mae']<=v['mae']*g['maximum_winter_mae_ratio'] for y,v in b['winters'].items()),
            every_region=all(c['regions'][k]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for k,v in b['regions'].items()),
            cold=c['cold']['mae']<=b['cold']['mae']*g['maximum_cold_mae_ratio'],date_sensitivity=result['bootstrap']['quantiles'][2]<0)
        assert gates==result['gates'] and all(gates.values())==result['primary_success']
    assert len(refits)==4 and len(summary['fits'])==12
    assert verify_preserved()==summary['preservation']==recorded['preservation']
    write(out/'independent_verification.json',dict(status='passed',summary_sha256=sha(out/'summary.json'),
        feature_values=checked,maximum_equivalence_difference=maximum,prefix_bit_exact_feature_values=prefix_values,
        prediction_values=pred_values,metric_checks=metric_checks,exact_refits=refits,
        audit_sha256=sha(Path(__file__)),preservation=summary['preservation']))
    print('VERIFIED',checked,prefix_values,pred_values,metric_checks,len(refits),flush=True)


if __name__=='__main__':main()
