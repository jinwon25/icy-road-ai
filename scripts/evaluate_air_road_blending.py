"""고정 72개 결합을 이중 공간 제외 예측으로 선택하고 외부 그룹에 적용한다."""
from datetime import datetime,timezone
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from scripts.audit_qa633_development import reference
from scripts.benchmark_submission_baselines import counts
from src.data_source import sha256_file as sha
from src.method_blending import domain,ALLOWED
from src.submission_runtime import FEATURES
from src.air_road_blending import policies,predict_policy,current_rule,validate_model_origin,event_context,event_report,select_policy
from src.qa633_metrics import daily_table,aggregate

PRIVATE=ROOT/'outputs/private';SOURCE=PRIVATE/'weather_memory_controls_20261013_v1'
OUT=PRIVATE/'air_road_blending_20261016_v1';CONFIG=ROOT/'config/air_road_blending_experiment.json'
WEATHER=['asos_air_temp','aws_air_temp','aws_humidity','aws_dewpoint','rain15_max_3h','asos_snow_cm','asos_age_minutes','aws_age_minutes']


def report(frame,prediction,context,minimums=(144,1)):
    p=np.asarray(prediction,dtype=np.int8);pop=sorted(frame.station.unique())
    r=counts(frame,p);r['event']=event_report(context,p)
    valid=frame.ice.eq(1).to_numpy();r['station_tp']={s:int((valid&frame.station.eq(s).to_numpy()&(p==1)).sum()) for s in pop}
    frame['_evaluation_prediction']=p
    r['daily']={str(n):reference(frame,'_evaluation_prediction',pop,n)[0] for n in minimums}
    frame.drop(columns='_evaluation_prediction',inplace=True)
    return r


def fixed_comparators(frame):
    return dict(current=current_rule(frame),air_zero=(frame.asos_air_temp.to_numpy()<=0).astype(np.int8),
        always_one=np.ones(len(frame),np.int8),road_zero=(frame.road_prediction.to_numpy()<=0).astype(np.int8),
        always_zero=np.zeros(len(frame),np.int8))


def main():
    if OUT.exists():raise FileExistsError('Preserve completed rule experiment')
    frozen=preservation();plan=read(CONFIG);specs=policies(plan);OUT.mkdir()
    write(OUT/'experiment_plan.json',plan|{'started_at_utc':datetime.now(timezone.utc).isoformat()})
    paths=[CONFIG,Path(__file__),ROOT/'src/air_road_blending.py',ROOT/'src/qa633_metrics.py',
        SOURCE/'summary.json',SOURCE/'independent_verification.json',SOURCE/'fit_receipts.json',SOURCE/'groups.json',
        PRIVATE/'weather_distance_20261010_v1/development_inputs.parquet',
        PRIVATE/'qa633_development_20261013_v1/fixed_predictions.parquet']
    assert read(paths[5])['summary_sha256']==sha(paths[4])
    for name,digest in read(SOURCE/'input_signatures.json').items():assert sha(ROOT/name)==digest,name
    groups=read(SOURCE/'groups.json');write(OUT/'groups.json',groups);write(OUT/'policies.json',specs)
    records=read(SOURCE/'fit_receipts.json');registry={}
    for record in records:
        path=SOURCE/record['model_path'];assert sha(path)==record['model_sha256'];paths.append(path)
        assert record['features']==list(FEATURES)
        assert set(record['training_stations'])==set(ALLOWED)-set(record['forbidden_stations'])
        registry[(record['candidate'],tuple(sorted(record['excluded_groups'])))]=record
    weather=domain(pd.read_parquet(paths[8],columns=['station','time',*WEATHER]))
    for name in ['asos_age_minutes','aws_age_minutes']:
        assert (weather[name].isna()|weather[name].gt(0)).all()
    labels=domain(pd.read_parquet(paths[9],columns=['station','time','ice']))
    saved_current=pd.read_parquet(paths[9],columns=['station','time','equal_nohistory_pair'])
    decisions={};outer_parts=[];inner_report_count=0
    for outer in sorted(groups):
        frames={}
        for kind in ['inner_oof','outer_predictions']:
            path=SOURCE/outer/(kind+'.parquet');paths.append(path)
            f=pd.read_parquet(path,columns=['station','time','group','nohistory12_mse300','nohistory12_mae300','equal_nohistory_pair'])
            f=f.merge(labels,on=['station','time'],validate='one_to_one').merge(weather,on=['station','time'],validate='one_to_one')
            f=f.sort_values(['station','time']).reset_index(drop=True);domain(f)
            expected_groups=set(groups)-{outer} if kind=='inner_oof' else {outer}
            assert set(f.group)==expected_groups
            for target in expected_groups:
                assert set(f.loc[f.group.eq(target),'station'])==set(groups[target])
                for name in ['nohistory12_mse300','nohistory12_mae300']:
                    record=registry[(name,tuple(sorted({outer,target})))];validate_model_origin(record,groups,outer,target)
            f['road_prediction']=(f.nohistory12_mse300+f.nohistory12_mae300)/2
            np.testing.assert_array_equal(f.road_prediction,f.equal_nohistory_pair)
            for name,p in fixed_comparators(f).items():f[name]=p
            for name,spec in specs.items():f[name]=predict_policy(f,spec)
            frames[kind]=f
        inner=frames['inner_oof'];context=event_context(inner,inner.current)
        comparators={name:report(inner,inner[name],context) for name in fixed_comparators(inner)}
        reports={name:report(inner,inner[name],context) for name in specs};inner_report_count+=(len(reports)+len(comparators))*2
        choice={}
        for track in ['research','strict']:
            chosen,accepted=select_policy(reports,comparators,track,outer,sorted(set(groups)-{outer}))
            choice[track]=dict(chosen=chosen,accepted=accepted,selection_groups=sorted(set(groups)-{outer}),outer_labels_used=False)
        decisions[outer]=dict(tracks=choice,comparators=comparators,reports=reports)
        folder=OUT/outer;folder.mkdir();write(folder/'selection.json',decisions[outer])
        inner.to_parquet(folder/'inner_inputs_and_predictions.parquet',index=False,compression='zstd')
        external=frames['outer_predictions']
        for track in ['research','strict']:
            external['nested_'+track]=external[choice[track]['chosen']]
            external['chosen_'+track]=choice[track]['chosen']
        external['outer_group']=outer;outer_parts.append(external)
        print(outer,{track:(v['chosen'],len(v['accepted'])) for track,v in choice.items()},flush=True)
    combined=pd.concat(outer_parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    check=combined.merge(saved_current,on=['station','time'],validate='one_to_one',suffixes=('','_saved'))
    np.testing.assert_array_equal(check.current,check.equal_nohistory_pair_saved)
    assert len(combined)==155257 and combined.ice.notna().sum()==155118
    combined.to_parquet(OUT/'outer_predictions.parquet',index=False,compression='zstd')
    context=event_context(combined,combined.current)
    comparisons=[*fixed_comparators(combined),'nested_research','nested_strict']
    reports={name:report(combined,combined[name],context,(144,130,72,1) if name in comparisons else (144,1))
        for name in [*fixed_comparators(combined),*specs,'nested_research','nested_strict']}
    day_parts=[];station_parts=[]
    for name in comparisons:
        for minimum in [144,130,72,1]:
            days=daily_table(combined,combined[name],sorted(combined.station.unique()),minimum)
            summary,stations=aggregate(days,sorted(combined.station.unique()))
            for key,value in summary.items():
                old=reports[name]['daily'][str(minimum)][key]
                if isinstance(value,float):assert np.isclose(value,old,rtol=0,atol=1e-12),(name,key)
                else:assert value==old,(name,key)
            day_parts.append(days.assign(method=name,minimum_valid_slots=minimum))
            station_parts.append(stations.assign(method=name,minimum_valid_slots=minimum))
    pd.concat(day_parts).to_csv(OUT/'comparison_daily.csv',index=False)
    pd.concat(station_parts).to_csv(OUT/'comparison_station.csv',index=False)
    best=max(specs,key=lambda name:reports[name]['daily']['144']['f1_available_station_mean'])
    write(OUT/'decisions.json',decisions);write(OUT/'input_signatures.json',{str(p.relative_to(ROOT)):sha(p) for p in paths})
    assert preservation()==frozen
    write(OUT/'summary.json',dict(status='air_road_rule_blending_complete',finished_at_utc=datetime.now(timezone.utc).isoformat(),
        policies=len(specs),rows=len(combined),reports=reports,choices={g:{t:d['tracks'][t]['chosen'] for t in ['research','strict']} for g,d in decisions.items()},
        retrospective_best_fixed_policy=best,retrospective_best_is_not_an_independent_estimate=True,
        inner_metric_reports=inner_report_count,outer_metric_reports=sum(len(r['daily']) for r in reports.values()),
        new_model_fits=0,reused_temperature_models=len(records),model_promoted=False,new_independent_assessment=False,
        protected_or_opened_assessment_outcomes_read=False,old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],
        execution_candidate_archive_sha256=sha(PRIVATE/'submission_candidate_20261016_v1.zip'),
        files={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file()}))
    for name in [*comparisons,best]:
        r=reports[name];print(name,'F1',r['daily']['144']['f1_available_station_mean'],'FP/FN',r['fp'],r['fn'],'lost',r['event']['lost_events'],flush=True)


if __name__=='__main__':main()
