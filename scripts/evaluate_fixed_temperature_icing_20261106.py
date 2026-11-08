"""저장된 지역 제외 온도로 두 고정 결빙 규칙을 평가한다. 학습·문턱 탐색 없음."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_objective_icing import verify_preserved
from scripts.evaluate_icing_snow_age_20261106 import reports_for
from scripts.evaluate_official_icing_upgrade_20261106 import block
W=ROOT/'outputs/private/fixed_temperature_icing_20261106'
B=ROOT/'outputs/private/competition_submission/icy_road_model'
SOURCE=ROOT/'outputs/private/solar_history_curve_20261024_v1/combined_asos_solar_mae1200'

def write(p,v):
    with p.open('x',encoding='utf8') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

def main():
    W.mkdir(exist_ok=True);assert not (W/'summary.json').exists()
    preserved=verify_preserved()
    paths=[B/'results/evaluation/development_predictions.parquet',SOURCE/'predictions.parquet']
    plan=dict(at_utc=datetime.now(timezone.utc).isoformat(),
        rules={'baseline':'기존 12특성 기준온도와 수분 조건',
               'temperature63':'기존 63특성 지역 제외 예측 <= 0°C, 해당 온도의 이슬점 조건 또는 기존 강수·적설 조건',
               'joint_temperature':'baseline과 temperature63을 모두 만족'},
        missing_temperature_policy='63특성 예측이 없으면 baseline 유지',
        new_models=0,thresholds_searched=0,temperature_threshold_c=0,
        gates=dict(precision_minimum_absolute_gain=.0025,f1_minimum_absolute_gain=.001,
            minimum_recall_ratio=.95,minimum_detected_event_ratio=.98,
            each_winter_f1_not_lower=True,each_region_f1_maximum_decline=.001,
            strict144_precision_and_f1_not_lower=True,day_block_f1_delta_lower_percentile_positive=True),
        source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in paths},
        protected_outcomes_used=False,external_four_outcomes_used=False,
        new_independent_assessment=False,production_model_changed=False)
    if (W/'plan.json').exists():
        previous=json.loads((W/'plan.json').read_text('utf8'))
        assert {k:v for k,v in previous.items() if k!='at_utc'}=={k:v for k,v in plan.items() if k!='at_utc'}
    else:write(W/'plan.json',plan)
    base=pd.read_parquet(paths[0]).sort_values(['station','time']).reset_index(drop=True)
    original=pd.read_parquet(paths[1]).sort_values(['station','time']).reset_index(drop=True)
    assert len(set(base.station))==9 and not set(base.station)&{'12410','33411','23402','33402','33406','12213','23411'}
    fit_audit=[]
    for group,q in original.groupby('group'):
        r=json.loads((SOURCE/(group+'.json')).read_text('utf8'))
        assert not set(r['training_stations'])&set(q.station)
        assert sha(SOURCE/(group+'.joblib'))==r['model_sha256']
        assert sha(SOURCE/(group+'.parquet'))==r['prediction_sha256']
        fit_audit.append(dict(excluded_group=group,excluded_stations=sorted(set(q.station)),features=len(r['features']),model_sha256=r['model_sha256']))
    f=base.merge(original[['station','time','prediction','ice','road_temp']],on=['station','time'],how='left',validate='one_to_one',suffixes=['','_source'])
    np.testing.assert_array_equal(f.ice,f.ice_source);np.testing.assert_array_equal(f.road_temp,f.road_temp_source)
    input_rows=len(f)
    f=f.loc[np.isfinite(f.physical_both)&f.ice.isin([0,1])].reset_index(drop=True)
    assert len(f)==309928 and np.isfinite(f.physical_both).all()
    f['baseline']=f.physical_both
    f['available']=True
    dew=f.aws_dewpoint.ge(f.prediction)&f.aws_age_minutes.between(0,60,inclusive='right')
    wet=dew|f.rain15_max_3h.gt(0)|f.asos_snow_cm.gt(0)
    f['temperature63']=np.where(f.prediction.notna(),(f.prediction.le(0)&wet).astype(float),f.baseline)
    f['joint_temperature']=(f.baseline.eq(1)&f.temperature63.eq(1)).astype(float)
    reports={};days={};events={}
    for name in plan['rules']:
        report,day,event=reports_for(f,name)
        reports[name]=report;days[name]=day[1];events[name]=event
        event.to_csv(W/(name+'_events.csv'),index=False)
        day[1].to_csv(W/(name+'_days.csv'),index=False)
        print(name,{k:report['1'][k] for k in ['precision','recall','f1','tp','fp','fn']},flush=True)
    np.testing.assert_allclose(reports['baseline']['1']['precision'],.04485598292497128,rtol=0,atol=1e-12)
    gates={};sens={}
    old=reports['baseline'];g=plan['gates']
    for name in ['temperature63','joint_temperature']:
        r=reports[name]
        sens[name]=block(days[name],days['baseline'],2026110619)
        gates[name]=dict(
            precision=r['1']['precision']>=old['1']['precision']+g['precision_minimum_absolute_gain'],
            f1=r['1']['f1']>=old['1']['f1']+g['f1_minimum_absolute_gain'],
            recall=r['1']['recall']>=g['minimum_recall_ratio']*old['1']['recall'],
            events=r['events']['candidate_detected']>=g['minimum_detected_event_ratio']*old['events']['candidate_detected'],
            winters=all(r['winters'][str(y)]['f1']>=old['winters'][str(y)]['f1'] for y in [2024,2025]),
            regions=all(r['regions'][group]['f1']>=old['regions'][group]['f1']-g['each_region_f1_maximum_decline'] for group in old['regions']),
            strict144=all(r['144'][k]>=old['144'][k] for k in ['precision','f1']),
            calendar_sensitivity=sens[name]['difference_percentiles'][0]>0)
    rows=[]
    for name,r in reports.items():
        for scope,report in [('all',r['1']),('strict144',r['144']),*[(y,v) for y,v in r['winters'].items()],*r['regions'].items()]:
            rows.append(dict(rule=name,scope=scope,**{k:report[k] for k in ['precision','recall','f1','tp','fp','fn']}))
    pd.DataFrame(rows).to_csv(W/'comparison.csv',index=False)
    f[['station','time','group','winter','ice','road_temp','temperature_both','prediction','baseline','temperature63','joint_temperature']].to_parquet(W/'predictions.parquet',index=False,compression='zstd')
    summary=dict(status='fixed_rule_development_comparison_complete',reports=reports,promotion_gates=gates,
        passed_candidates=[n for n,g in gates.items() if all(g.values())],sensitivity=sens,
        region_exclusion_audits=fit_audit,new_model_fits=0,threshold_searches=0,
        input_rows=input_rows,common_rows=len(f),observed_ice=int(f.ice.sum()),fallback_rows=int(f.prediction.isna().sum()),
        protected_outcomes_used=False,external_four_outcomes_used=False,new_independent_assessment=False,
        production_model_changed=False,predictions_sha256=sha(W/'predictions.parquet'))
    assert verify_preserved()==preserved
    write(W/'summary.json',summary)
    print(json.dumps(dict(gates=gates,passed_candidates=summary['passed_candidates']),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
