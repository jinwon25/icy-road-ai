"""새 기상 결합의 고정 서리 규칙을 예측 봉인 후 기존 개발9곳에서 반증한다."""
import gc
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved,report,fixed_calendar_f1,block_sensitivity
from src.road_weather_transfer import features,baselines
from src.weather_history_stable import stable_temporal_features
from src.frost_icing import frost_policies
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def main():
    cfg=ROOT/'config/frost_icing_20261101.json';plan=read(cfg);out=ROOT/plan['output']
    if out.exists():raise FileExistsError('Preserve frost study')
    frozen=verify_preserved();humidity=ROOT/plan['humidity_study'];air=ROOT/plan['air_study']
    for folder in [humidity,air]:
        audit=read(folder/'independent_verification.json');assert audit['status']=='passed' and audit['summary_sha256']==sha(folder/'summary.json')
    selection=read(ROOT/plan['temperature_selection']);assert selection['status']=='audited_final_selection'
    assert len(selection['components'])==1 and selection['weights']==[1.0]
    component=selection['components'][0];temp=ROOT/component['folder']/'predictions.parquet'
    assert sha(temp)==component['predictions_sha256']
    inputs=[cfg,Path(__file__),ROOT/'src/frost_icing.py',ROOT/'src/weather_thermodynamics.py',
        ROOT/plan['weather_inputs'],ROOT/plan['labels'],ROOT/plan['temperature_selection'],temp,
        humidity/'summary.json',air/'summary.json']
    out.mkdir(parents=True);write(out/'plan.json',dict(at_utc=now(),settings=plan,signatures={p.relative_to(ROOT).as_posix():sha(p) for p in inputs},preservation=frozen))
    columns=[c for c in pq.ParquetFile(ROOT/plan['weather_inputs']).schema.names if c not in ['air_temperature','relative_humidity','wind_speed']]
    f=pd.read_parquet(ROOT/plan['weather_inputs'],columns=columns,filters=[('group','!=','competition')]).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations']) and f.station.nunique()==9
    index=pd.read_parquet(ROOT/plan['labels'],columns=['station','time','available','asos_air_temp'],filters=[('station','in',sorted(f.station.unique()))])
    f=f.merge(index[['station','time','available']],on=['station','time'],how='left',validate='one_to_one')
    assert f.available.notna().all()
    surface=pd.read_parquet(temp,columns=['station','time','prediction'])
    f=f.merge(surface.rename(columns={'prediction':'estimated_road_temperature'}),on=['station','time'],how='left',validate='one_to_one')
    x,history=stable_temporal_features(f)
    _,near_air=baselines(f,'air_temperature');_,near_rh=baselines(f,'relative_humidity')
    result=f[['station','time','group','winter','available','asos_air_temp','estimated_road_temperature']].copy()
    result['estimated_air_temperature']=np.nan;result['estimated_relative_humidity']=np.nan;models=[]
    for held,part in f.groupby('group'):
        for target,study,path,column,design,base in [
            ('air_temperature',air,air/'air_temperature'/('residual_hgb_'+held+'.joblib'),'estimated_air_temperature',x,near_air),
            ('relative_humidity',humidity,humidity/'spatial'/(held+'.joblib'),'estimated_relative_humidity',history,near_rh)]:
            meta=read(path.with_suffix('.json'));assert sha(path)==meta['model_sha256']
            assert not set(part.station)&set(meta['training_stations'])
            model=joblib.load(path)
            with deny_network() as attempts,threadpool_limits(limits=2):values=model.predict(design.loc[part.index])+base[part.index]
            assert not attempts
            if target=='relative_humidity':values=np.clip(values,0,100)
            result.loc[part.index,column]=values
            models.append(dict(target=target,held=held,path=path.relative_to(ROOT).as_posix(),sha256=sha(path),training_stations=meta['training_stations']))
            del model
    wet=x.aws_rain_15m.gt(0)|x.asos_snow_cm.gt(0)
    predictions,flags=frost_policies(f.asos_air_temp,near_air,near_rh,f.estimated_road_temperature,
        result.estimated_air_temperature,result.estimated_relative_humidity,wet,f.available)
    for name,value in {**predictions,**flags}.items():result[name]=value
    assert np.all(result.loc[result.asos_zero.eq(1),'union_frost_estimates'].eq(1))
    result.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    write(out/'prediction_seal.json',dict(at_utc=now(),predictions_sha256=sha(out/'predictions.parquet'),models=models,
        icing_labels_loaded_in_this_run=False,policy_selection_performed=False,baseline_alerts_preserved=True))
    del x,history,f;gc.collect()
    labels=pd.read_parquet(ROOT/plan['labels'],columns=['station','time','ice'],filters=[('station','in',sorted(result.station.unique()))])
    result=result.merge(labels,on=['station','time'],how='left',validate='one_to_one')
    result.to_parquet(out/'evaluation.parquet',index=False,compression='zstd');reports={};days={}
    for name in predictions:
        reports[name],days[name],events=report(result,name,plan)
        days[name].to_csv(out/(name+'_daily.csv'),index=False,encoding='utf-8-sig')
        events.to_csv(out/(name+'_events.csv'),index=False,encoding='utf-8-sig')
    for name in reports:reports[name]['baseline_calendar_f1']=fixed_calendar_f1(days[name],days['asos_zero'])
    chosen=plan['primary_candidate'];boot=block_sensitivity(days[chosen],days['asos_zero'],plan['seed'])
    a=reports[chosen];b=reports['asos_zero'];g=plan['primary_gates']
    checks=dict(f1=a['all']['f1_fixed_population']>=b['all']['f1_fixed_population']*(1+g['minimum_relative_f1_gain']),
        precision=a['all']['precision_available_station_mean']>=b['all']['precision_available_station_mean'],
        recall=a['all']['recall_available_station_mean']>=b['all']['recall_available_station_mean'],
        winters=all(a['winters'][y]['f1_fixed_population']>=b['winters'][y]['f1_fixed_population'] for y in b['winters']),
        regions=all(a['regions'][r]['f1_fixed_population']>=b['regions'][r]['f1_fixed_population'] for r in b['regions']),
        events=a['events']['lost_events']<=g['lost_events_maximum'],date_block_lower=boot['difference_percentiles'][0]>g['date_block_lower_delta_f1'])
    reference=read(ROOT/'outputs/private/transferred_air_icing_20261031_v1/summary.json')['reports']['asos_zero']
    for key in ['f1_fixed_population','valid_rows','tp','fp','fn']:
        np.testing.assert_allclose(b['all'][key],reference['all'][key],rtol=0,atol=1e-12)
    assert verify_preserved()==frozen
    write(out/'summary.json',dict(status='fixed_frost_icing_complete',reports=reports,sensitivity=boot,primary_gates=checks,
        primary_success=all(checks.values()),production_model_changed=False,new_independent_assessment=False,preservation=frozen,
        files={p.relative_to(out).as_posix():sha(p) for p in out.iterdir() if p.is_file()}))
    print('FROST COMPLETE',a['all']['f1_fixed_population'],checks,flush=True)


if __name__=='__main__':main()
