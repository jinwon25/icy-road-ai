"""지역 제외 기온 모형의 고정 0°C 정책을 결빙 정답 개봉 전에 봉인하고 반증한다."""
from datetime import datetime, timezone
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from src.road_weather_transfer import features,baselines
from scripts.evaluate_objective_icing import (read,write,verify_preserved,report,
    fixed_calendar_f1,block_sensitivity)


def main():
    cfg=ROOT/'config/transferred_air_icing_20261031.json';plan=read(cfg);out=ROOT/plan['output']
    if out.exists():raise FileExistsError('Preserve transferred-air icing comparison')
    study=ROOT/plan['weather_study'];audit=read(study/'independent_verification.json');summary=read(study/'summary.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(study/'summary.json')
    assert summary['reports']['air_temperature']['primary_success']
    frozen=verify_preserved();out.mkdir(parents=True)
    files=[cfg,Path(__file__),ROOT/plan['weather_inputs'],ROOT/plan['labels'],
           study/'summary.json',study/'independent_verification.json',ROOT/'src/road_weather_transfer.py',
           ROOT/'src/blind_icing.py',ROOT/'scripts/evaluate_objective_icing.py']
    write(out/'plan.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),settings=plan,
        signatures={p.relative_to(ROOT).as_posix():sha(p) for p in files},preservation=frozen))
    # 기상 목표까지 포함된 연구 입력에서도 순수 기상과 메타데이터만 읽는다.
    import pyarrow.parquet as pq
    columns=[c for c in pq.ParquetFile(ROOT/plan['weather_inputs']).schema.names
             if c not in ['air_temperature','relative_humidity','wind_speed']]
    f=pd.read_parquet(ROOT/plan['weather_inputs'],columns=columns)
    assert not set(f.station)&set(plan['blocked_stations'])
    f=f.loc[f.group.ne('competition')].sort_values(['station','time']).reset_index(drop=True)
    index=pd.read_parquet(ROOT/plan['labels'],columns=['station','time','available','asos_air_temp'])
    assert not set(index.station)&set(plan['blocked_stations'])
    f=f.merge(index[['station','time','available']],on=['station','time'],how='left',validate='one_to_one')
    assert f.available.notna().all();x=features(f);_,baseline=baselines(f,'air_temperature')
    result=f[['station','time','group','winter','available','asos_air_temp']].copy()
    result['estimated_air_temperature']=np.nan;models=[]
    for held,q in f.groupby('group'):
        name=plan['model'].format(held=held);path=study/name
        record=read(path.with_suffix('.json'));assert sha(path)==record['model_sha256']
        assert not set(q.station)&set(record['training_stations'])
        model=joblib.load(path)
        with deny_network() as attempts,threadpool_limits(limits=2):
            predictions=model.predict(x.loc[q.index])+baseline[q.index]
            repeat=joblib.load(path).predict(x.loc[q.index])+baseline[q.index]
        assert not attempts
        np.testing.assert_array_equal(predictions,repeat)
        assert np.isfinite(predictions[q.available]).all()
        result.loc[q.index,'estimated_air_temperature']=predictions
        models.append(dict(held=held,path=name,sha256=sha(path),training_stations=record['training_stations'],
                           query_stations=sorted(q.station.unique()),query_rows=len(q)))
    result['asos_zero']=np.where(result.available,result.asos_air_temp.le(0),np.nan)
    result['estimated_air_zero']=np.where(result.available,result.estimated_air_temperature.le(plan['threshold_c']),np.nan)
    result.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    write(out/'prediction_seal.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),predictions_sha256=sha(out/'predictions.parquet'),
        models=models,threshold=plan['threshold_c'],icing_labels_loaded_in_this_run=False,
        scope='repeated_development_only_not_independent_blind_test'))
    # 이후에만 허용 개발 9곳의 기존 결빙 정답을 연다. 미래·보호 정답은 읽지 않는다.
    labels=pd.read_parquet(ROOT/plan['labels'],columns=['station','time','ice'],filters=[('station','in',sorted(f.station.unique()))])
    assert set(labels.station)==set(f.station) and len(set(f.station))==9
    result=result.merge(labels,on=['station','time'],how='left',validate='one_to_one')
    result.to_parquet(out/'evaluation.parquet',index=False,compression='zstd')
    reports={};days={}
    for name in ['asos_zero','estimated_air_zero']:
        reports[name],days[name],events=report(result,name,plan)
        days[name].to_csv(out/(name+'_daily.csv'),index=False,encoding='utf-8-sig')
        events.to_csv(out/(name+'_events.csv'),index=False,encoding='utf-8-sig')
    for name in reports:reports[name]['baseline_calendar_f1']=fixed_calendar_f1(days[name],days['asos_zero'])
    sensitivity=block_sensitivity(days['estimated_air_zero'],days['asos_zero'],plan['seed'])
    a=reports['estimated_air_zero'];b=reports['asos_zero'];g=plan['primary_gates']
    checks=dict(f1=a['all']['f1_fixed_population']>=b['all']['f1_fixed_population']*(1+g['minimum_relative_f1_gain']),
        precision=a['all']['precision_available_station_mean']>=b['all']['precision_available_station_mean'],
        winters=all(a['winters'][y]['f1_fixed_population']>=b['winters'][y]['f1_fixed_population'] for y in b['winters']),
        regions=all(a['regions'][r]['f1_fixed_population']>=b['regions'][r]['f1_fixed_population'] for r in b['regions']),
        events=a['events']['lost_events']<=g['lost_events_maximum'],
        date_block_lower=sensitivity['difference_percentiles'][0]>g['date_block_lower_delta_f1'])
    # 기존 동일 개발 기준선과 행 수·분모·F1이 같은지 다시 대조한다.
    reference=read(ROOT/'outputs/private/objective_icing_20261031_v2/summary.json')['reports']['asos_zero']
    for key in ['f1_fixed_population','valid_rows','complete_or_accepted_days','tp','fp','fn']:
        np.testing.assert_allclose(b['all'][key],reference['all'][key],rtol=0,atol=1e-12)
    assert verify_preserved()==frozen
    value=dict(status='transferred_air_icing_complete',reports=reports,sensitivity=sensitivity,
        primary_gates=checks,primary_success=all(checks.values()),production_model_changed=False,
        new_independent_assessment=False,preservation=frozen,
        prediction_seal_sha256=sha(out/'prediction_seal.json'),
        files={p.relative_to(out).as_posix():sha(p) for p in out.iterdir() if p.is_file()})
    write(out/'summary.json',value)
    print('RESULT',a['all'],a['events'],checks,flush=True)


if __name__=='__main__':main()
