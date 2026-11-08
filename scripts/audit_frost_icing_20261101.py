"""서리 규칙 전량 재추론·별도 수식·일별지표·사건·기준선 보존을 검산한다."""
from pathlib import Path
import sys
import gc
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved,block_sensitivity
from scripts.audit_icing_transition import independent_metrics,independent_events
from scripts.audit_road_weather_transfer import compare
from src.weather_history_stable import stable_temporal_features
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def main():
    plan=read(ROOT/'config/frost_icing_20261101.json');out=ROOT/plan['output'];summary=read(out/'summary.json')
    if (out/'independent_verification.json').exists():raise FileExistsError('Preserve audit')
    recorded=read(out/'plan.json');seal=read(out/'prediction_seal.json')
    assert seal['icing_labels_loaded_in_this_run'] is False
    for name,h in recorded['signatures'].items():assert sha(ROOT/name)==h,name
    for name,h in summary['files'].items():assert sha(out/name)==h,name
    columns=[c for c in pq.ParquetFile(ROOT/plan['weather_inputs']).schema.names if c not in ['air_temperature','relative_humidity','wind_speed']]
    f=pd.read_parquet(ROOT/plan['weather_inputs'],columns=columns,filters=[('group','!=','competition')]).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations']) and f.station.nunique()==9
    p=pd.read_parquet(out/'predictions.parquet')
    pd.testing.assert_frame_equal(f[['station','time']],p[['station','time']],check_exact=True)
    actual=pd.read_parquet(out/'evaluation.parquet');pd.testing.assert_frame_equal(actual[p.columns],p,check_exact=True)
    labels=pd.read_parquet(ROOT/plan['labels'],columns=['station','time','available','ice'],filters=[('station','in',sorted(f.station.unique()))])
    labels=f[['station','time']].merge(labels,on=['station','time'],validate='one_to_one')
    np.testing.assert_array_equal(p.available,labels.available);np.testing.assert_array_equal(actual.ice,labels.ice)
    x,h=stable_temporal_features(f);checked=0
    for record in seal['models']:
        path=ROOT/record['path'];assert sha(path)==record['sha256']
        assert not set(record['training_stations'])&set(f.loc[f.group.eq(record['held']),'station'])
        select=f.group.eq(record['held']);target=record['target'];field='air_temp' if target=='air_temperature' else 'humidity'
        a=f['asos_'+field].where((f.asos_age_minutes>0)&(f.asos_age_minutes<=60)).to_numpy()
        b=f['aws_'+field].where((f.aws_age_minutes>0)&(f.aws_age_minutes<=15)).to_numpy()
        base=np.where(np.isfinite(b),b,a);model=joblib.load(path)
        with deny_network() as attempts,threadpool_limits(limits=2):
            v=model.predict((x if target=='air_temperature' else h).loc[select])+base[select]
        assert not attempts
        if field=='humidity':v=np.clip(v,0,100)
        np.testing.assert_array_equal(v,p.loc[select,'estimated_air_temperature' if field=='air_temp' else 'estimated_relative_humidity'])
        checked+=len(v);del model
    selection=read(ROOT/plan['temperature_selection']);item=selection['components'][0]
    temp=ROOT/item['folder']/'predictions.parquet';assert sha(temp)==item['predictions_sha256']
    t=pd.read_parquet(temp,columns=['station','time','prediction'])
    t=f[['station','time']].merge(t,on=['station','time'],how='left',validate='one_to_one')
    np.testing.assert_array_equal(t.prediction,p.estimated_road_temperature)
    baseline=p.asos_air_temp.to_numpy()<=0;road=p.estimated_road_temperature.to_numpy();available=p.available.to_numpy(bool)
    decisions={}
    for name,air,rh in [('estimates',p.estimated_air_temperature.to_numpy(),p.estimated_relative_humidity.to_numpy()),
        ('nearest',x.aws_air_temp.fillna(x.asos_air_temp).to_numpy(),x.aws_humidity.fillna(x.asos_humidity).to_numpy())]:
        valid=(air>=-80)&(air<=60)&(rh>=0)&(rh<=100)
        with np.errstate(divide='ignore',invalid='ignore'):
            pressure=611.21*np.exp(17.502*(air-.01)/(air+240.96))*rh/100
            ratio=np.log(np.where(valid&(pressure>0),pressure/611.21,np.nan))
            point=(273.85*ratio+.22587)/(22.587-ratio)
        good=np.isfinite(point)&(point>=-80)&(point<=60)&np.isfinite(road)
        np.testing.assert_array_equal(good,p[name+'_physical_available'])
        np.testing.assert_allclose(point,p[name+'_frost_point_c'],atol=1e-11,rtol=1e-12,equal_nan=True)
        frost=(road<=0)&(road<=point);value=np.where(good,frost,baseline)
        decisions['frost_'+name]=np.where(available,value,np.nan)
        decisions['union_frost_'+name]=np.where(available,baseline|value,np.nan)
        if name=='estimates':
            wet=x.aws_rain_15m.gt(0).to_numpy()|x.asos_snow_cm.gt(0).to_numpy()
            decisions['wet_or_frost']=np.where(available,np.where(good,(road<=0)&(frost|wet),baseline),np.nan)
    decisions['asos_zero']=np.where(available,baseline,np.nan)
    del x,h,f;gc.collect();metric_checks=0
    for name,value in decisions.items():
        np.testing.assert_array_equal(value,p[name]);checked+=len(value)
        independent=independent_metrics(actual,value);reported=summary['reports'][name]
        for key in independent:metric_checks+=compare(independent[key],reported['all'][key])
        metric_checks+=compare(independent_events(actual,value,actual.asos_zero),reported['events'])
    # 검증의 주 기준인 두 겨울·지역 평균도 별도 집계 경로로 대조한다.
    for name in decisions:
        for year,part in actual.groupby('winter'):
            stats=independent_metrics(part,part[name]);saved=summary['reports'][name]['winters'][str(year)]
            for key in stats:metric_checks+=compare(stats[key],saved[key])
        for region,part in actual.groupby('group'):
            stats=independent_metrics(part,part[name]);saved=summary['reports'][name]['regions'][region]
            for key in stats:metric_checks+=compare(stats[key],saved[key])
    primary=plan['primary_candidate'];a=actual[primary].to_numpy();b=actual.asos_zero.to_numpy()
    assert np.all(a[b==1]==1)
    valid=actual.available&actual.ice.isin([0,1]);added=valid&actual[primary].eq(1)&actual.asos_zero.eq(0)
    counts=dict(additional_positive_rows=int((added&actual.ice.eq(1)).sum()),additional_false_positive_rows=int((added&actual.ice.eq(0)).sum()),
        baseline_alert_rows=int((b==1).sum()),baseline_alerts_removed=int(np.sum((b==1)&(a!=1))))
    days={name:pd.read_csv(out/(name+'_daily.csv'),float_precision='round_trip') for name in ['asos_zero',primary]}
    compare(block_sensitivity(days[primary],days['asos_zero'],plan['seed']),summary['sensitivity'])
    assert verify_preserved()==summary['preservation']
    write(out/'independent_verification.json',dict(status='passed',summary_sha256=sha(out/'summary.json'),
        replayed_values=checked,metric_checks=metric_checks,primary_additional_alerts=counts,
        no_new_icing_fit=True,no_threshold_selection=True,audit_sha256=sha(Path(__file__))))
    print('FROST VERIFIED',checked,metric_checks,counts,flush=True)


if __name__=='__main__':main()
