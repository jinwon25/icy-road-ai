"""허용 개발 예측을 단순 기준선과 동일 날짜·지점 모집단에서 비교한다."""
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read, write, preservation
from scripts.audit_qa633_development import reference
from scripts.audit_temperature_blind_validation import compare
from src.data_source import sha256_file as sha
from src.method_blending import domain
from src.qa633_metrics import daily_table, aggregate
from src.submission_metadata import temperature_evidence

PRIVATE=ROOT/'outputs/private'
OUT=PRIVATE/'baseline_benchmark_20261016_v1'
SOURCES=[PRIVATE/'qa633_development_20261013_v1/fixed_predictions.parquet',
         PRIVATE/'weather_memory_controls_20261013_v1/ice_predictions.parquet',
         PRIVATE/'weather_distance_20261010_v1/development_inputs.parquet',
         PRIVATE/'weather_memory_controls_20261013_v1/groups.json']


def counts(frame, prediction):
    y=frame.ice.to_numpy(float); p=np.asarray(prediction); valid=np.isfinite(y)
    tp=int((valid & (y==1) & (p==1)).sum()); fp=int((valid & (y==0) & (p==1)).sum())
    fn=int((valid & (y==1) & (p==0)).sum()); tn=int((valid & (y==0) & (p==0)).sum())
    return dict(n=int(valid.sum()),tp=tp,fp=fp,fn=fn,tn=tn,
        recall=tp/(tp+fn) if tp+fn else None,
        precision=tp/(tp+fp) if tp+fp else None,
        f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)


def main():
    if OUT.exists(): raise FileExistsError('Preserve completed benchmark')
    frozen=preservation(); OUT.mkdir()
    write(OUT/'analysis_plan.json',dict(created_at_utc=datetime.now(timezone.utc).isoformat(),
        baseline_rules=['always_zero','always_one','asos_air_temp_le_zero','estimated_road_temp_le_zero'],
        fixed_rules_no_threshold_search=True,minimum_valid_slots=[144,130,72,1],
        diagnostic_only=True,promotion_requires_unopened_station_validation=True,
        missing_simple_temperature_rule='0 for fixed development benchmark, same convention as existing fixed binary predictions; delivery output remains null',
        common_support_diagnostic='Both-zero F1=0 on all coverage-accepted days; supplemental, not an official policy change',
        sources={str(p.relative_to(ROOT)):sha(p) for p in SOURCES}))
    f=domain(pd.read_parquet(SOURCES[0],columns=['station','time','ice','equal_nohistory_pair','equal_distance_mse_mae300']))
    f=f.rename(columns={'equal_nohistory_pair':'current','equal_distance_mse_mae300':'previous_trio'})
    temp=domain(pd.read_parquet(SOURCES[1],columns=['station','time','road_temp','equal_nohistory_pair']))
    pop=sorted(f.station.unique()); temp=temp.loc[temp.station.isin(pop)].copy()
    weather=domain(pd.read_parquet(SOURCES[2],columns=['station','time','asos_air_temp']))
    f=f.merge(temp.rename(columns={'equal_nohistory_pair':'estimated_temp'}),on=['station','time'],validate='one_to_one')
    f=f.merge(weather,on=['station','time'],validate='one_to_one')
    assert len(f)==155257 and f.ice.notna().sum()==155118 and len(pop)==9
    f['always_zero']=0; f['always_one']=1
    f['asos_air_temp_le_zero']=(f.asos_air_temp<=0).astype(int)
    f['estimated_road_temp_le_zero']=(f.estimated_temp<=0).astype(int)
    methods=['current','previous_trio','always_zero','always_one','asos_air_temp_le_zero','estimated_road_temp_le_zero']
    reports={}; daily_rows=[]; station_rows=[]; group_rows=[]; checked_reports=0
    groups=read(SOURCES[3])
    for method in methods:
        coverage={}
        for minimum in [144,130,72,1]:
            days=daily_table(f,f[method],pop,minimum); summary,stations=aggregate(days,pop)
            expected, ref_stations, ref_days=reference(f,method,pop,minimum)
            compare(expected,summary)
            pd.testing.assert_frame_equal(days[ref_days.columns],ref_days,check_exact=False,atol=1e-12,rtol=0)
            pd.testing.assert_frame_equal(stations[ref_stations.columns],ref_stations,check_exact=False,atol=1e-12,rtol=0)
            checked_reports+=1
            coverage[str(minimum)]=summary
            daily_rows.append(days.assign(method=method,minimum_valid_slots=minimum))
            station_rows.append(stations.assign(method=method,minimum_valid_slots=minimum))
        days=daily_table(f,f[method],pop,144)
        accepted=days.loc[days.coverage_accepted].copy()
        common_macro=float(accepted.assign(f1_zero=accepted.f1.fillna(0)).groupby('station').f1_zero.mean().mean())
        positive=accepted.loc[accepted.actual_ice_slots.gt(0)]
        positive_macro=float(positive.groupby('station').f1.mean().mean())
        for label,stations in [('all',pop),('without_33408',[s for s in pop if s!='33408']),*groups.items()]:
            take=f.station.isin(stations); group_rows.append(dict(method=method,population=label,**counts(f.loc[take],f.loc[take,method])))
        reports[method]=dict(counts=counts(f,f[method]),coverage=coverage,
            supplemental_common_coverage_day_f1_zero=common_macro,
            supplemental_actual_ice_day_f1=positive_macro,
            missing_rule_input_rows=int(f.asos_air_temp.isna().sum()) if method=='asos_air_temp_le_zero' else int(f.estimated_temp.isna().sum()) if method=='estimated_road_temp_le_zero' else 0)
    daily=pd.concat(daily_rows,ignore_index=True); stations=pd.concat(station_rows,ignore_index=True)
    daily.to_csv(OUT/'daily_comparison.csv',index=False); stations.to_csv(OUT/'station_comparison.csv',index=False)
    pd.DataFrame(group_rows).to_csv(OUT/'group_comparison.csv',index=False)
    f.to_parquet(OUT/'fixed_comparator_predictions.parquet',index=False,compression='zstd')
    evidence=temperature_evidence(temp)
    current=reports['current']; always=reports['always_one']
    # 사용자 검토 기록과 별도 재집계가 같은 결과인지 확인한다.
    user=read(PRIVATE/'analyst_review_20261016_v1/review_evidence.json')
    assert all(current['counts'][k]==user['development_counts'][k] for k in current['counts'])
    assert abs(current['coverage']['144']['f1_available_station_mean']-user['daily_comparators']['current']['f1_available_station_mean'])<1e-12
    assert abs(always['coverage']['144']['f1_available_station_mean']-user['daily_comparators']['always_one']['f1_available_station_mean'])<1e-12
    share=float((f.ice.eq(1)&f.station.eq('33408')).sum()/f.ice.eq(1).sum())
    ratio=(always['counts']['fp']-current['counts']['fp'])/(current['counts']['fn']-always['counts']['fn'])
    files={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in OUT.iterdir() if p.is_file()}
    assert preservation()==frozen
    write(OUT/'summary.json',dict(status='fixed_baseline_benchmark_independently_verified',
        completed_at_utc=datetime.now(timezone.utc).isoformat(),population=pop,rows=len(f),reports=reports,
        temperature=evidence,positive_share_33408=share,fp_fn_cost_break_even_miss_to_false_alarm=ratio,
        current_beats_always_one_daily_f1=False,performance_qualified=False,new_model_fits=0,
        independent_reference_reports=checked_reports,verified_daily_rows=len(daily),verified_station_rows=len(stations),
        protected_or_opened_assessment_outcomes_read=False,model_promoted=False,files=files,
        old_frozen_files=frozen[0],reserved_frozen_files=frozen[1]))
    print(json.dumps({m:{'daily_f1':reports[m]['coverage']['144']['f1_available_station_mean'],
        'f1_days':reports[m]['coverage']['144']['f1_days'],'fp':reports[m]['counts']['fp'],'fn':reports[m]['counts']['fn']} for m in methods},indent=2))


if __name__=='__main__': main()
