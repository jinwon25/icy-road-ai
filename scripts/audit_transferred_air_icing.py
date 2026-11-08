"""고정 기온 정책의 사전 봉인·지역 제외 추론·결빙 지표를 별도로 대조한다."""
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.road_weather_runtime import INPUT_COLUMNS
from src.road_weather_transfer import features,baselines
from src.offline_runtime import deny_network
from scripts.evaluate_objective_icing import read,write,verify_preserved
from scripts.audit_icing_transition import independent_metrics,independent_events


def main():
    out=ROOT/'outputs/private/transferred_air_icing_20261031_v1';destination=out/'independent_verification.json'
    if destination.exists():raise FileExistsError('Preserve transferred-air audit')
    plan=read(out/'plan.json');settings=plan['settings'];summary=read(out/'summary.json');seal=read(out/'prediction_seal.json')
    for p,h in plan['signatures'].items():assert sha(ROOT/p)==h,p
    for p,h in summary['files'].items():assert sha(out/p)==h,p
    assert seal['icing_labels_loaded_in_this_run'] is False and seal['threshold']==0
    assert sha(out/'predictions.parquet')==seal['predictions_sha256']
    p=pd.read_parquet(out/'predictions.parquet');evaluation=pd.read_parquet(out/'evaluation.parquet')
    pd.testing.assert_frame_equal(p,evaluation[p.columns],check_exact=True)
    assert not set(p.station)&set(settings['blocked_stations'])
    data=pd.read_parquet(ROOT/settings['weather_inputs'],columns=['station','time','group']+INPUT_COLUMNS)
    f=p[['station','time']].merge(data,on=['station','time'],how='left',validate='one_to_one')
    x=features(f);_,baseline=baselines(f,'air_temperature');count=0
    for record in seal['models']:
        q=f.loc[f.group.eq(record['held'])];path=ROOT/settings['weather_study']/record['path']
        assert sha(path)==record['sha256'] and not set(q.station)&set(record['training_stations'])
        with deny_network() as attempts,threadpool_limits(limits=2):
            prediction=joblib.load(path).predict(x.loc[q.index])+baseline[q.index]
        assert not attempts
        np.testing.assert_array_equal(prediction,p.loc[q.index,'estimated_air_temperature']);count+=len(q)
    np.testing.assert_array_equal(np.where(p.available,p.estimated_air_temperature.to_numpy()<=0,np.nan),p.estimated_air_zero)
    np.testing.assert_array_equal(np.where(p.available,p.asos_air_temp.to_numpy()<=0,np.nan),p.asos_zero)
    checks=0
    for name in ['asos_zero','estimated_air_zero']:
        m=independent_metrics(evaluation,evaluation[name]);report=summary['reports'][name]
        for key in ['f1_fixed_population','precision_available_station_mean','recall_available_station_mean','tp','fp','fn']:
            np.testing.assert_allclose(m[key],report['all'][key],atol=1e-12,rtol=0);checks+=1
        assert independent_events(evaluation,evaluation[name],evaluation.asos_zero)==report['events'];checks+=5
    # 각 겨울 120일의 동일 7일 블록을 두 정책·아홉 지점에 함께 적용한다.
    indices=[]
    for year in [0,1]:
        starts=np.random.default_rng(settings['seed']+year).integers(0,120,(2000,18))
        indices.append(np.array([[int((s+j)%120)+120*year for s in row for j in range(7)][:120] for row in starts]))
    ids=np.concatenate(indices,axis=1);values={}
    for name in ['asos_zero','estimated_air_zero']:
        d=pd.read_csv(out/(name+'_daily.csv'));assert len(d)==2160
        a=d.f1.to_numpy().reshape(9,240);finite=np.isfinite(a)
        numerator=np.nan_to_num(a)[:,ids].sum(axis=-1);denominator=finite[:,ids].sum(axis=-1)
        values[name]=np.divide(numerator,denominator,out=np.zeros_like(numerator),where=denominator>0).mean(axis=0)
    delta=values['estimated_air_zero']-values['asos_zero']
    np.testing.assert_allclose(np.quantile(delta,[.025,.5,.975]),summary['sensitivity']['difference_percentiles'],atol=1e-12,rtol=0)
    assert verify_preserved()==plan['preservation']
    write(destination,dict(status='passed',summary_sha256=sha(out/'summary.json'),models_replayed=4,
        prediction_values=count,metric_event_checks=checks,date_bootstrap_draws=2000,
        audit_source_sha256=sha(Path(__file__)),production_model_changed=False))
    print('TRANSFERRED AIR AUDIT PASSED',count,checks,flush=True)


if __name__=='__main__':main()
