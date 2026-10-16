"""별도 시간창·사건 집계와 저장 모델 재추론으로 기온·노면 결합을 검산한다."""
from datetime import datetime,timezone
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from scripts.audit_temperature_blind_validation import compare
from src.qa633_metrics import daily_table,aggregate
from src.data_source import sha256_file as sha
from src.method_blending import domain
from src.submission_runtime import FEATURES

PRIVATE=ROOT/'outputs/private';OUT=PRIVATE/'air_road_blending_20261016_v1'
SOURCE=PRIVATE/'weather_memory_controls_20261013_v1'


def oracle_current(f):
    water=(f.aws_dewpoint>=f.road_prediction)|(f.rain15_max_3h>0)|(f.asos_snow_cm>0)
    return (f.road_prediction.notna()&(f.road_prediction<=0)&water).astype('int8').to_numpy()


def oracle_policy(f,spec):
    temperature=f.asos_air_temp if spec['source']=='air' else .5*f.asos_air_temp+.5*f.road_prediction
    condition=temperature.notna()&temperature.le(spec['threshold'])
    if spec['moisture']=='humidity80':condition&=f.aws_humidity.ge(80)
    elif spec['moisture']=='dew_or_precip':
        condition&=(f.aws_air_temp-f.aws_dewpoint).le(2)|f.rain15_max_3h.gt(0)|f.asos_snow_cm.gt(0)
    if spec['slots']==3:
        result=pd.Series(False,index=f.index)
        for _,part in f.groupby('station'):
            values=pd.Series(condition.loc[part.index].to_numpy(float),index=pd.DatetimeIndex(part.time))
            result.loc[part.index]=values.rolling('30min',min_periods=3,closed='right').sum().eq(3).to_numpy()
        condition=result
    if spec['union']:condition|=pd.Series(oracle_current(f),index=f.index).eq(1)
    return condition.astype('int8').to_numpy()


def oracle_event(f,p):
    positive=f.loc[f.ice.eq(1),['station','time']].copy()
    positive['new_event']=positive.station.ne(positive.station.shift())|positive.time.diff().ne(pd.Timedelta(minutes=10))
    positive['event_id']=positive.new_event.cumsum()
    positive['p']=np.asarray(p)[f.ice.eq(1).to_numpy()]
    positive['current']=oracle_current(f)[f.ice.eq(1).to_numpy()]
    events=positive.groupby('event_id').agg(slots=('p','size'),prediction=('p','sum'),current=('current','sum'))
    old=events.current.gt(0);detected=events.prediction.gt(0);lost=old&~detected
    return dict(events=len(events),baseline_detected=int(old.sum()),detected=int(detected.sum()),
        lost_events=int(lost.sum()),gained_events=int((~old&detected).sum()),lost_single_slot_events=int((lost&events.slots.eq(1)).sum()))


def oracle_report(f,p,minimums):
    labels=f.ice.to_numpy(float);prediction=np.asarray(p);valid=np.isfinite(labels)
    tp=int(((labels==1)&(prediction==1)).sum());fp=int(((labels==0)&(prediction==1)).sum())
    fn=int(((labels==1)&(prediction==0)).sum());tn=int(((labels==0)&(prediction==0)).sum())
    result=dict(n=int(valid.sum()),tp=tp,fp=fp,fn=fn,tn=tn,precision=tp/(tp+fp) if tp+fp else None,
        recall=tp/(tp+fn) if tp+fn else None,f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)
    result['station_tp']=f.assign(_tp=(labels==1)&(prediction==1)).groupby('station')._tp.sum().astype(int).to_dict()
    result['event']=oracle_event(f,p);result['daily']={}
    for minimum in minimums:
        days=daily_table(f,p,sorted(f.station.unique()),int(minimum))
        result['daily'][minimum]=aggregate(days,sorted(f.station.unique()))[0]
    return result


def oracle_eligible(r,refs,track):
    for condition in ['144','1']:
        value=r['daily'][condition]['f1_available_station_mean']
        if value is None:return False
        if any(refs[name]['daily'][condition]['f1_available_station_mean'] is None or
            value<=refs[name]['daily'][condition]['f1_available_station_mean']+1e-12 for name in ['current','air_zero','always_one']):return False
    current=refs['current']
    if r['event']['lost_events']!=0 or any(r['station_tp'][s]<v for s,v in current['station_tp'].items()):return False
    if track=='research':return r['fp']<=refs['air_zero']['fp']
    if r['fp']>current['fp'] or r['fn']>current['fn']:return False
    for condition in ['144','1']:
        for metric in ['precision','recall','f1']:
            key=metric+'_available_station_mean';a=r['daily'][condition][key];b=current['daily'][condition][key]
            if a is None or b is None or a+1e-12<b:return False
    return True


def main():
    target=OUT/'independent_verification.json'
    if target.exists():raise FileExistsError('Preserve completed rule audit')
    frozen=preservation();summary=read(OUT/'summary.json');groups=read(OUT/'groups.json');specs=read(OUT/'policies.json')
    for name,digest in read(OUT/'input_signatures.json').items():assert sha(ROOT/name)==digest,name
    for name,digest in summary['files'].items():assert sha(OUT/name)==digest,name
    plan=read(OUT/'experiment_plan.json');plan.pop('started_at_utc')
    assert plan==read(ROOT/'config/air_road_blending_experiment.json') and len(specs)==72
    receipts=read(SOURCE/'fit_receipts.json');registry={(r['candidate'],tuple(sorted(r['excluded_groups']))):r for r in receipts}
    weather=domain(pd.read_parquet(PRIVATE/'weather_distance_20261010_v1/development_inputs.parquet',columns=['station','time',*FEATURES]))
    models={};predictions_checked=0;temperature_values=0;metric_reports=0;event_reports=0;decisions=read(OUT/'decisions.json')
    def audit_temperature(f,outer):
        nonlocal temperature_values
        for target_group,part in f.groupby('group'):
            forbidden={outer,target_group};blocked=set().union(*(set(groups[g]) for g in forbidden))
            inputs=part[['station','time']].merge(weather,on=['station','time'],validate='one_to_one')
            assert len(inputs)==len(part)
            for name in ['nohistory12_mse300','nohistory12_mae300']:
                key=(name,tuple(sorted(forbidden)));r=registry[key]
                assert set(r['forbidden_stations'])==blocked and not blocked&set(r['training_stations'])
                path=SOURCE/r['model_path'];assert sha(path)==r['model_sha256']
                if key not in models:models[key]=joblib.load(path)
                with threadpool_limits(limits=2):values=models[key].predict(inputs[list(FEATURES)])
                values=np.where(np.isfinite(inputs.asos_air_temp),values,np.nan)
                np.testing.assert_allclose(values,part[name],equal_nan=True,atol=0,rtol=0)
                temperature_values+=len(part)
    def verify(f,reports):
        nonlocal predictions_checked,metric_reports,event_reports
        for name,spec in specs.items():
            np.testing.assert_array_equal(oracle_policy(f,spec),f[name]);predictions_checked+=len(f)
        comparators={'current':oracle_current(f),'air_zero':f.asos_air_temp.le(0).astype('int8').to_numpy(),
            'always_one':np.ones(len(f),dtype='int8'),'road_zero':f.road_prediction.le(0).astype('int8').to_numpy(),
            'always_zero':np.zeros(len(f),dtype='int8')}
        for name,value in comparators.items():np.testing.assert_array_equal(value,f[name])
        verified={}
        for name,r in reports.items():
            expected=oracle_report(f,f[name],list(r['daily']));compare(expected,r)
            verified[name]=expected;metric_reports+=len(r['daily']);event_reports+=1
        return verified
    for outer in sorted(groups):
        f=domain(pd.read_parquet(OUT/outer/'inner_inputs_and_predictions.parquet'))
        assert set(f.station)==set().union(*(set(v) for k,v in groups.items() if k!=outer))
        audit_temperature(f,outer)
        expected=verify(f,{**decisions[outer]['comparators'],**decisions[outer]['reports']})
        refs={n:expected[n] for n in decisions[outer]['comparators']}
        for track in ['research','strict']:
            accepted=[n for n in specs if oracle_eligible(expected[n],refs,track)]
            chosen=min(accepted,key=lambda n:(-expected[n]['daily']['144']['f1_available_station_mean'],expected[n]['fp'],n)) if accepted else ('air_zero' if track=='research' else 'current')
            assert chosen==decisions[outer]['tracks'][track]['chosen']
            assert accepted==decisions[outer]['tracks'][track]['accepted']
        print('inner audited',outer,flush=True)
    combined=domain(pd.read_parquet(OUT/'outer_predictions.parquet'))
    for outer,part in combined.groupby('outer_group'):
        assert set(part.station)==set(groups[outer]);audit_temperature(part,outer)
        for track in ['research','strict']:
            chosen=decisions[outer]['tracks'][track]['chosen']
            np.testing.assert_array_equal(part['nested_'+track],part[chosen])
    verify(combined,summary['reports'])
    saved_days=pd.read_csv(OUT/'comparison_daily.csv',dtype={'station':str},parse_dates=['date_kst'])
    saved_stations=pd.read_csv(OUT/'comparison_station.csv',dtype={'station':str})
    for name in saved_days.method.unique():
        for minimum in [144,130,72,1]:
            days=daily_table(combined,combined[name],sorted(combined.station.unique()),minimum)
            _,stations=aggregate(days,sorted(combined.station.unique()))
            a=saved_days.loc[saved_days.method.eq(name)&saved_days.minimum_valid_slots.eq(minimum)].reset_index(drop=True)
            b=saved_stations.loc[saved_stations.method.eq(name)&saved_stations.minimum_valid_slots.eq(minimum)].reset_index(drop=True)
            # 항상 비결빙의 전부 미정의인 Precision은 메모리에서 object/None,
            # CSV에서는 float/NaN이므로 같은 수치 결측 표현으로 맞춰 대조한다.
            for column in ['precision','recall','f1']:
                b[column]=pd.to_numeric(b[column],errors='raise').astype(float)
                stations[column]=pd.to_numeric(stations[column],errors='raise').astype(float)
            pd.testing.assert_frame_equal(a[days.columns],days,atol=1e-12,rtol=0,check_exact=False)
            pd.testing.assert_frame_equal(b[stations.columns],stations,atol=1e-12,rtol=0,check_exact=False)
    assert preservation()==frozen
    assert sha(PRIVATE/'submission_candidate_20261016_v1.zip')==summary['execution_candidate_archive_sha256']
    result=dict(status='independent_air_road_blending_audit_passed',audited_at_utc=datetime.now(timezone.utc).isoformat(),
        summary_sha256=sha(OUT/'summary.json'),fixed_policy_prediction_values_verified=predictions_checked,
        temperature_component_values_replayed=temperature_values,reused_models_verified=len(models),
        metric_reports_verified=metric_reports,event_reports_verified=event_reports,selection_groups_verified=4,
        saved_daily_rows_verified=len(saved_days),saved_station_rows_verified=len(saved_stations),
        new_model_fits=0,assessment_outcomes_read=False,execution_candidate_unchanged=True,
        old_frozen_files=frozen[0],reserved_frozen_files=frozen[1])
    write(target,result);print(result,flush=True)


if __name__=='__main__':main()
