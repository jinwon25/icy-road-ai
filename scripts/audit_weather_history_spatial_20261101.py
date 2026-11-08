"""목표별 지역 제외 4모형·기존 4모형·대표2재학습·지표·분할·봉인을 검산한다."""
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved
from scripts.audit_road_weather_transfer import measure,compare
from scripts.audit_weather_temporal import bootstrap
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def report(f,column):
    return dict(pooled=measure(f,column),winters={str(y):measure(q,column) for y,q in f.groupby('winter')},
        regions={g:measure(q,column) for g,q in f.groupby('group')},cold=measure(f.loc[f.cold_input],column))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'config/weather_air_history_spatial_20261101.json')
    args=parser.parse_args();config=args.config.resolve();plan=read(config);target=plan['target']
    assert target in ['air_temperature','relative_humidity','wind_speed']
    out=ROOT/plan['output'];source=ROOT/plan['source'];baseline=ROOT/plan['baseline']
    summary=read(out/'summary.json');recorded=read(out/'plan.json')
    if (out/'independent_verification.json').exists():raise FileExistsError('Preserve completed spatial audit')
    temporal_audit=read(source/'independent_verification.json')
    assert temporal_audit['status']=='passed' and temporal_audit['summary_sha256']==sha(source/'summary.json')
    for name,digest in recorded['signatures'].items():assert sha(ROOT/name)==digest,name
    for name,digest in summary['files'].items():assert sha(out/name)==digest,name
    temporal=read(source/'summary.json')
    for name in ['instant_residual_features.parquet','history_residual_features.parquet']:
        assert sha(source/name)==temporal['files'][name]
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations']) and not {'ice','road_temp','state_raw'}&set(f)
    field={'air_temperature':'air_temp','relative_humidity':'humidity','wind_speed':'wind_speed'}[target]
    asos=f['asos_'+field].where((f.asos_age_minutes>0)&(f.asos_age_minutes<=60)).to_numpy()
    aws=f['aws_'+field].where((f.aws_age_minutes>0)&(f.aws_age_minutes<=15)).to_numpy()
    nearest=np.where(np.isfinite(aws),aws,asos)
    available=np.isfinite(asos)&np.isfinite(nearest);good=available&np.isfinite(f[target])
    p=pd.read_parquet(out/'predictions.parquet')
    idx=pd.MultiIndex.from_frame(f[['station','time']]).get_indexer(pd.MultiIndex.from_frame(p[['station','time']]))
    assert (idx>=0).all() and len(set(idx))==len(idx)
    np.testing.assert_array_equal(np.sort(idx),np.flatnonzero(available&f.group.ne('competition')))
    np.testing.assert_array_equal(p.observed,f.loc[idx,target])
    np.testing.assert_array_equal(p.asos,asos[idx]);np.testing.assert_array_equal(p.aws_fallback,nearest[idx])
    np.testing.assert_array_equal(p.cold_input,np.abs(f.loc[idx,'asos_air_temp'])<=3)
    values=0;refits=[]
    for spec in summary['fits']:
        held=spec['held'];train=good&f.group.ne(held);query=available&f.group.eq(held)
        assert not set(f.loc[train,'station'])&set(f.loc[query,'station'])
        assert spec['training_rows']==int(train.sum()) and spec['query_rows']==int(query.sum())
        assert spec['training_stations']==sorted(f.loc[train,'station'].unique())
        assert set(f.loc[train,'winter'])=={2024,2025}
        refitting=held in ['honam_baekyang','seohaean_seocheon']
        for candidate,model_path in [('instant_residual',baseline/target/('residual_hgb_'+held+'.joblib')),
            ('history_residual',out/(held+'.joblib'))]:
            model=joblib.load(model_path)
            assert sha(model_path)==spec['reference_model_sha256' if candidate=='instant_residual' else 'model_sha256']
            assert all(model.get_params()[k]==v for k,v in plan['model'].items())
            x=pd.read_parquet(source/(candidate+'_features.parquet'))
            assert list(model.feature_names_in_)==list(x)
            query_x=x.loc[query]
            if candidate=='history_residual' and refitting:train_x=x.loc[train]
            del x;gc.collect();pa.default_memory_pool().release_unused()
            with deny_network() as attempts,threadpool_limits(limits=2):actual=model.predict(query_x)+nearest[query]
            assert not attempts
            if target=='relative_humidity':actual=np.clip(actual,0,100)
            elif target=='wind_speed':actual=np.maximum(actual,0)
            np.testing.assert_array_equal(actual,p.loc[p.group.eq(held),candidate]);values+=len(actual)
            if candidate=='history_residual':
                np.testing.assert_array_equal(actual,np.load(out/(held+'.npy'),allow_pickle=False))
                if refitting:
                    count=f.loc[train].groupby(['station','winter']).station.transform('size').to_numpy(float)
                    weights=1/count;weights/=weights.mean()
                    refit=HistGradientBoostingRegressor(**plan['model'])
                    with deny_network() as attempts,threadpool_limits(limits=2):
                        refit.fit(train_x,f.loc[train,target].to_numpy()-nearest[train],sample_weight=weights)
                        replay=refit.predict(query_x)+nearest[query]
                    assert not attempts
                    if target=='relative_humidity':replay=np.clip(replay,0,100)
                    elif target=='wind_speed':replay=np.maximum(replay,0)
                    np.testing.assert_array_equal(replay,actual)
                    refits.append(held);del refit,train_x
            del model,query_x;gc.collect();pa.default_memory_pool().release_unused()
            print('AUDIT',held,candidate,flush=True)
    q=p.loc[p.observed.notna()];checks=0
    for candidate in ['asos','aws_fallback','instant_residual','history_residual']:
        checks+=compare(report(q,candidate),summary['reports'][candidate])
    checks+=compare(bootstrap(q,'history_residual','instant_residual',plan['bootstrap']),summary['bootstrap'])
    c=summary['reports']['history_residual'];b=summary['reports']['instant_residual'];g=plan['gates']
    gates=dict(pooled=c['pooled']['mae']<=b['pooled']['mae']*(1-g['minimum_mae_reduction']),
        both_winters=all(c['winters'][y]['mae']<=v['mae']*g['maximum_winter_mae_ratio'] for y,v in b['winters'].items()),
        every_region=all(c['regions'][k]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for k,v in b['regions'].items()),
        cold=c['cold']['mae']<=b['cold']['mae']*g['maximum_cold_mae_ratio'],date_sensitivity=summary['bootstrap']['quantiles'][2]<0)
    assert gates==summary['gates'] and all(gates.values())==summary['primary_success']
    assert verify_preserved()==summary['preservation']==recorded['preservation']
    write(out/'independent_verification.json',dict(status='passed',summary_sha256=sha(out/'summary.json'),
        audit_script_sha256=sha(Path(__file__)),prediction_values=values,metric_checks=checks,
        exact_refits=refits,production_model_changed=False,preservation=summary['preservation']))
    print('VERIFIED',values,checks,refits,flush=True)


if __name__=='__main__':main()
