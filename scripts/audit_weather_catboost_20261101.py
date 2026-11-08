"""CatBoost12모형·고정평균·대표2재학습·두 검증의 모든 수치와 봉인을 검산한다."""
from pathlib import Path
import sys
import gc
from catboost import CatBoostRegressor
import numpy as np
import pandas as pd
import pyarrow as pa
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved
from scripts.audit_weather_history_spatial_20261101 import report
from scripts.audit_weather_temporal import bootstrap
from scripts.audit_road_weather_transfer import compare
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def main():
    plan=read(ROOT/'config/weather_catboost_20261101.json');out=ROOT/plan['output'];old=ROOT/plan['baseline'];s=read(out/'summary.json')
    if (out/'independent_verification.json').exists():raise FileExistsError('Preserve audit')
    for name,digest in read(out/'plan.json')['signatures'].items():assert sha(ROOT/name)==digest,name
    for name,digest in s['files'].items():assert sha(out/name)==digest,name
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations'])
    a=f.asos_humidity.where((f.asos_age_minutes>0)&(f.asos_age_minutes<=60)).to_numpy()
    b=f.aws_humidity.where((f.aws_age_minutes>0)&(f.aws_age_minutes<=15)).to_numpy()
    nearest=np.where(np.isfinite(b),b,a);y=f.relative_humidity.to_numpy();good=np.isfinite(y)&np.isfinite(a)&np.isfinite(nearest)
    replayed=0;refits=0;metric_checks=0;accepted=[]
    for mode in ['joint','spatial']:
        p=pd.read_parquet(out/mode/'predictions.parquet');prior=pd.read_parquet(old/mode/'predictions.parquet')
        pd.testing.assert_frame_equal(p[['station','time','observed','stable_history']],prior[['station','time','observed','stable_history']],check_exact=True)
        np.testing.assert_array_equal(p.half_hgb_catboost,(p.stable_history+p.catboost_history)/2)
        for candidate in plan['candidates']:
            measure=report(p,candidate);boot=bootstrap(p,candidate,'stable_history',plan['bootstrap'])
            metric_checks+=compare(measure,s['reports'][mode]['candidates'][candidate]['metrics'])
            metric_checks+=compare(boot,s['reports'][mode]['candidates'][candidate]['bootstrap'])
            base=report(p,'stable_history');g=plan['gates']
            gates=dict(pooled=measure['pooled']['mae']<=base['pooled']['mae']*(1-g['minimum_mae_reduction']),
                both_winters=all(measure['winters'][z]['mae']<=v['mae'] for z,v in base['winters'].items()),
                every_region=all(measure['regions'][z]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for z,v in base['regions'].items()),
                cold=measure['cold']['mae']<=base['cold']['mae'],date_sensitivity=boot['quantiles'][2]<0)
            assert gates==s['reports'][mode]['candidates'][candidate]['gates']
        for record in [r for r in s['fits'] if r['mode']==mode]:
            held=record['held'];year=record['query_winter'];train=good&f.group.ne(held);query=good&f.group.eq(held)
            if year is not None:train&=f.winter.ne(year);query&=f.winter.eq(year)
            assert int(train.sum())==record['training_rows'] and int(query.sum())==record['query_rows']
            assert sorted(f.loc[train,'station'].unique())==record['training_stations'] and not set(record['training_stations'])&set(record['query_stations'])
            if year is not None:assert year not in record['training_winters']
            stem=held+('_'+str(year) if year is not None else '');path=out/mode/(stem+'.cbm')
            x=pd.read_parquet(old/'features.parquet');qx=x.loc[query]
            assert list(x)==record['features'] and len(list(x))==82
            model=CatBoostRegressor();model.load_model(str(path));assert model.feature_names_==list(x)
            with deny_network() as attempts,threadpool_limits(limits=2):
                raw=model.predict(qx,thread_count=2);values=np.clip(raw+nearest[query],0,100)
            assert not attempts
            np.testing.assert_array_equal(values,np.load(path.with_suffix('.npy'),allow_pickle=False))
            key=pd.MultiIndex.from_frame(f.loc[query,['station','time']])
            np.testing.assert_array_equal(values,p.set_index(['station','time']).loc[key,'catboost_history'])
            replayed+=len(values)
            if held=='honam_baekyang' and (year is None or year==2024):
                count=f.loc[train].groupby(['station','winter']).station.transform('size').to_numpy(float)
                weights=1/count;weights/=weights.mean();refit=CatBoostRegressor(**plan['model'])
                with deny_network() as attempts,threadpool_limits(limits=2):
                    refit.fit(x.loc[train],y[train]-nearest[train],sample_weight=weights)
                    np.testing.assert_array_equal(refit.predict(qx,thread_count=2),raw)
                assert not attempts;refits+=1;del refit;print('CAT REFIT',mode,flush=True)
            del x,qx,model;gc.collect();pa.default_memory_pool().release_unused()
    for candidate in plan['candidates']:
        if all(s['reports'][mode]['candidates'][candidate]['primary_success'] for mode in ['joint','spatial']):accepted.append(candidate)
    assert accepted==s['accepted_candidates'] and refits==2 and verify_preserved()==s['preservation']
    write(out/'independent_verification.json',dict(status='passed',summary_sha256=sha(out/'summary.json'),
        replayed_values=replayed,metric_checks=metric_checks,exact_refits=refits,accepted_candidates=accepted,audit_sha256=sha(Path(__file__))))
    print('CAT VERIFIED',replayed,metric_checks,refits,flush=True)


if __name__=='__main__':main()
