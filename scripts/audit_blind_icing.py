"""새 지역의 사전 봉인과 일회 평가를 별도 계산 경로로 검산한다."""
import argparse
from collections import Counter
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from src.anchored_icing import linear_features
from scripts.blind_icing_validation import DEFAULT, PRIVATE, verify, now, read, write
from scripts.fresh_station_validation import ensure_unopened,old_freezes
from scripts.audit_icing_transition import independent_metrics,independent_events


def audit_prediction(out):
    seal=verify(out);plan=read(out/'plan.json');ensure_unopened(PRIVATE,plan['new_stations'])
    if (out/'prediction_audit.json').exists():raise FileExistsError('Preserve pre-outcome audit')
    q=pd.read_parquet(out/'inputs.parquet');p=pd.read_parquet(out/'predictions.parquet');train=pd.read_parquet(out/'training.parquet')
    assert not {'ice','road_temp','state_raw'}&set(q)
    assert set(train.station).isdisjoint(set(q.station)) and len(set(train.station))==23
    assert set(q.station)==set(plan['new_stations']) and len(q)==138240 and not q.duplicated(['station','time']).any()
    pd.testing.assert_frame_equal(q[['station','time']],p[['station','time']])
    raw=pd.read_parquet(ROOT/plan['new_weather']/'asos_raw_fields.parquet')
    points=pd.read_csv(out/'points.csv',dtype={'station':str,'asos_station':str}).set_index('station')
    # pandas merge_asof 및 정규화 함수를 다시 쓰지 않고 직접 시각·값을 찾는다.
    fields={'TA':('air_temp',-60,70),'TS':('ground_temp',-60,70),'HM':('humidity',0,100),'RN':('rain_mm',0,500),
        'SD_TOT':('snow_cm',0,500),'CA_TOT':('cloud_tenths',0,10),'SI':('solar_mj_m2',0,10),'WS':('wind_speed',0,100),
        'TD':('dewpoint_obs',-80,50),'PA':('pressure',500,1100),'VS':('visibility',0,10000),'SD_HR3':('new_snow3h',0,500),'TE_005':('soil5cm',-60,80)}
    values_checked=0
    for station,g in q.groupby('station'):
        source=raw.loc[raw.STN.eq(points.loc[station,'asos_station'])].sort_values('time')
        st=source.time.to_numpy(dtype='datetime64[ns]');tt=g.time.to_numpy(dtype='datetime64[ns]')
        loc=np.searchsorted(st,tt,side='left')-1;safe=np.maximum(loc,0)
        age=(tt-st[safe])/np.timedelta64(1,'m');valid=(loc>=0)&(age>0)&(age<=60)
        expected=st[safe].copy();expected[~valid]=np.datetime64('NaT')
        np.testing.assert_array_equal(expected,g.asos_source_time.to_numpy(dtype='datetime64[ns]'))
        for code,(name,lo,hi) in fields.items():
            v=source[code].astype(float).to_numpy()[safe];v=np.where(valid&(v>=lo)&(v<=hi),v,np.nan)
            np.testing.assert_array_equal(v,g['asos_'+name]);values_checked+=len(v)
    assert np.array_equal(q.available,q.asos_air_temp.notna())
    f=train.loc[train.available&train.ice.isin([0,1])];keys=list(zip(f.station,f.winter,f.time.dt.date,f.ice))
    counts=Counter(keys);classes={};dates={}
    for s,w,d,y in counts:classes.setdefault((s,w,d),set()).add(y);dates.setdefault((s,w),set()).add(d)
    weights=np.array([1/(counts[k]*len(classes[k[:3]])*len(dates[k[:2]])) for k in keys]);weights/=weights.mean()
    receipt=read(out/'fit_receipt.json')
    np.testing.assert_allclose(float(np.average(f.ice,weights=weights)),receipt['weighted_positive_fraction'],atol=1e-14,rtol=0)
    x=linear_features(q)
    for r in receipt['models']:
        name=r['candidate'];path=out/(name+'.joblib');assert sha(path)==r['model_sha256']
        assert r['stations']==sorted(f.station.unique()) and r['rows']==len(f) and r['features']==list(x)
        model=joblib.load(path)
        with deny_network() as attempts,threadpool_limits(limits=2):score=model.predict_proba(x)[:,1]
        assert not attempts;np.testing.assert_array_equal(score,p[name+'_score'])
        expected=np.where(q.available,q.asos_air_temp.to_numpy()<=np.minimum(0,2*score-1),np.nan)
        np.testing.assert_array_equal(expected,p[name])
        if name.startswith('logit'):
            # 전처리 중앙값과 가중치가 새 지점의 분포를 사용하지 않았는지 확인한다.
            tx=linear_features(f);med=tx.median().fillna(0).to_numpy()
            np.testing.assert_allclose(model[0].statistics_,med,atol=1e-12,rtol=0)
            transformed=model[0].transform(tx)
            np.testing.assert_allclose(model[1].mean_,transformed.mean(axis=0),atol=1e-10,rtol=0)
    for name,threshold in [('asos_zero',0),('air_minus_half',-.5)]:
        np.testing.assert_array_equal(p[name],np.where(q.available,q.asos_air_temp.le(threshold),np.nan))
    write(out/'prediction_audit.json',dict(status='passed',audited_at_utc=now(),seal_sha256=sha(out/'prediction_seal.json'),
        rows=len(q),weather_values_checked=values_checked,models_replayed=2,training_weight_rows=len(f),
        new_outcomes_present=False,frozen_counts=list(old_freezes()),code_sha256=sha(Path(__file__))))
    print('PRE-OUTCOME AUDIT PASSED',values_checked,'weather values',flush=True)


def audit_result(out):
    verify(out);plan=read(out/'plan.json');summary=read(out/'summary.json')
    if (out/'result_audit.json').exists():raise FileExistsError('Preserve first result audit')
    f=pd.read_parquet(out/'evaluation.parquet');assert sha(out/'evaluation.parquet')==summary['evaluation_sha256']
    manifest=read(out/'download_manifest.json');assert sha(out/'download_manifest.json')==summary['manifest_sha256']
    assert manifest['first_request_utc']>read(out/'prediction_seal.json')['sealed_at_utc']
    assert read(out/'prediction_audit.json')['audited_at_utc']<manifest['first_request_utc']<manifest['completed_at_utc']<summary['evaluated_at_utc']
    checks=0
    for name in plan['candidate_names']:
        for year in ['144','2024','2025']:
            part=f if year=='144' else f.loc[f.winter.eq(int(year))]
            actual=independent_metrics(part,part[name]);expected=summary['reports'][name][year]
            for k in ['fp','tp','fn','f1_fixed_population','precision_available_station_mean','recall_available_station_mean']:
                if expected[k] is None:assert actual[k] is None
                else:np.testing.assert_allclose(actual[k],expected[k],atol=1e-12,rtol=0)
            checks+=1
        assert independent_events(f,f[name],f.asos_zero)==summary['reports'][name]['events']
    # 파케이로 정규화한 상태를 다시 매핑하여 양성/결측 처리가 임의 변경되지 않았는지 확인한다.
    observed=[];transport_checks=0
    for key,r in manifest['records'].items():
        path=out/'observations'/(key+'.parquet');assert sha(path)==r['sha256'];g=pd.read_parquet(path)
        assert set(g.station)<= {r['station']} and g.time.between(r['start_kst'],r['end_kst']).all()
        assert (g.time.dt.minute%10==0).all();observed.append(g[['station','time','state_raw','ice']])
        for t in r['transport']:
            assert sha(out/'transport'/t['transport_cache_path'])==t['transport_response_sha256'];transport_checks+=1
    g=pd.concat(observed,ignore_index=True)
    raw=pd.to_numeric(g.state_raw,errors='coerce')
    normalized=np.where(raw.eq(4),1.,np.where(raw.isin([1,2,3,10,11,12,13,14,15]),0.,np.nan))
    np.testing.assert_array_equal(g.ice,normalized)
    merged=f[['station','time','ice']].merge(g[['station','time','ice']],on=['station','time'],how='left',suffixes=('_eval','_raw'),validate='one_to_one')
    np.testing.assert_array_equal(merged.ice_eval,merged.ice_raw)
    assert summary['primary_success']==all(summary['primary_gates'].values())
    write(out/'result_audit.json',dict(status='passed',audited_at_utc=now(),metric_checks=checks,event_checks=4,
        observation_files=len(manifest['records']),transport_files_checked=transport_checks,observed_rows=len(g),
        summary_sha256=sha(out/'summary.json'),frozen_counts=list(old_freezes()),code_sha256=sha(Path(__file__))))
    print('RESULT AUDIT PASSED',checks,'metrics',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['prediction','result']);p.add_argument('--output',type=Path,default=DEFAULT)
    a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(PRIVATE.resolve()):raise ValueError('Private output required')
    {'prediction':audit_prediction,'result':audit_result}[a.phase](out)


if __name__=='__main__':main()
