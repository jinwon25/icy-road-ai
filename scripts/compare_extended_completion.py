"""완료 실험을 전수 목록화하고 사전 고정한 단순성·고정 평균 기준을 적용한다."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.extended_search import temperature_gate
from src.extended_comparison import block_sensitivity,physical_ice,event_retention
from src.runtime_metrics import runtime_daily
from scripts.evaluate_method_blending import preservation

PRIVATE=ROOT/'outputs/private'
STUDIES=['extended_search_20261024_v1','extended_thermal_search_20261024_v1','thermal_refinement_20261024_v1',
 'canonical_thermal_search_20261024_v1','canonical_thermal_curve_20261024_v1','canonical_history_search_20261024_v1',
 'canonical_history_seed20261025_v1','canonical_history_seed20261026_v1','local_mlp_search_20261024_v1',
 'terrain_thermal_search_20261024_v1','combined_thermal_history_20261024_v1','combined_history_curve_20261024_v1',
 'solar_memory_search_20261024_v1','solar_history_curve_20261024_v1','solar_seed20261025_v1','solar_seed20261026_v1','solar_loss_pair_20261024_v1']


def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError('Preserve final comparison')
    frozen=preservation();rulepath=ROOT/'config/extended_final_selection_20261024.json';rules=read(rulepath)
    basepath=PRIVATE/'two_winter_models_20261024_v1/runtime_predictions.parquet';f=pd.read_parquet(basepath)
    assert sha(basepath)==read(basepath.parent/'audit_runtime.json')['runtime_prediction_sha256']
    reports={};folders={};registry=[]
    for study in STUDIES:
        folder=PRIVATE/study;assert (folder/'summary.json').exists(),study
        plan=read(folder/'plan.json')
        for spec in plan['settings']['candidates']:
            name=spec['name'];path=folder/name/'report.json';r=read(path)
            assert name not in reports;reports[name]=r;folders[name]=folder/name
            registry.append(dict(study=study,candidate=name,features=spec.get('features','weather'),family=spec['family'],iterations=spec.get('iterations'),epochs=spec.get('epochs'),
                mae=r['regression']['pooled']['mae'],rmse=r['regression']['pooled']['rmse'],bias=r['regression']['pooled']['bias'],
                cold_mae=r['regression']['near_freezing']['mae'],eligible=r['eligible'],failed_gates=';'.join(k for k,v in r['gates'].items() if not v),report_sha256=sha(path)))
    gate=read(ROOT/'config/extended_search_20261024.json')['temperature_gate'];vectors={}
    def vector(name):
        if name not in vectors:
            data=pd.read_parquet(folders[name]/'predictions.parquet');pd.testing.assert_frame_equal(data[['station','time']],f[['station','time']]);vectors[name]=data.prediction.to_numpy(float)
        return vectors[name]
    capacities=[f'combined_asos_solar_mae{n}' for n in rules['solar_capacity_iterations']]
    eligible=[n for n in capacities if reports[n]['eligible']];best=min(eligible,key=lambda n:reports[n]['regression']['pooled']['mae'])
    bestmae=reports[best]['regression']['pooled']['mae'];margin=rules['minimum_material_gain']
    simple=next(n for n in eligible if reports[n]['regression']['pooled']['mae']<=bestmae*(1+margin))
    last_gain=1-reports[capacities[-1]]['regression']['pooled']['mae']/reports[capacities[-2]]['regression']['pooled']['mae']
    assert last_gain<margin,'Capacity still materially improving; do not claim practical saturation'
    target=reports['combined_target_solar_mae600']['regression']['pooled']['mae'];asos=reports['combined_asos_solar_mae600']['regression']['pooled']['mae']
    assert asos<=target*(1+margin),'ASOS geometry equivalence not met'
    ensembles={
      'asos_solar1200_three_seed_mean':['combined_asos_solar_mae1200','combined_asos_solar_mae1200_seed20261025','combined_asos_solar_mae1200_seed20261026'],
      'asos_solar1200_history1200_mean':['combined_asos_solar_mae1200','combined_history_mae1200'],
      'asos_solar1200_2400_mean':['combined_asos_solar_mae1200','combined_asos_solar_mae2400'],
      'asos_solar1200_loss_mean':read(ROOT/'config/solar_loss_pair_20261024.json')['fixed_pair']}
    blends={}
    for name,members in ensembles.items():
        vectors[name]=np.mean([vector(m) for m in members],axis=0);blends[name]=temperature_gate(f,vectors[name],f.temperature_both,gate)
    from scripts.compare_extended_candidates import PAIRS
    declared=PAIRS|read(ROOT/'config/extended_fixed_blends_20261024.json')['pairs']
    declared['canonical_history_three_seed_mean']=['canonical_history_mae600','canonical_history_mae600_seed20261025','canonical_history_mae600_seed20261026']
    earlier_blends={}
    for name,members in declared.items():
        v=np.mean([vector(m) for m in members],axis=0);earlier_blends[name]=temperature_gate(f,v,f.temperature_both,gate)
    for weight,label in [(.5,'half'),(.75,'quarter')]:
        v=weight*np.mean([vector(m) for m in declared['thermal_equal']],axis=0)+(1-weight)*f.temperature_both.to_numpy()
        earlier_blends['thermal_equal_plus_v2_'+label]=temperature_gate(f,v,f.temperature_both,gate)
    selectable=[n for n,r in blends.items() if r['eligible'] and r['regression']['pooled']['mae']<=reports[simple]['regression']['pooled']['mae']*(1-margin)]
    chosen=min(selectable,key=lambda n:blends[n]['regression']['pooled']['mae']) if selectable else simple
    components=ensembles[chosen] if chosen in ensembles else [chosen];prediction=np.mean([vector(m) for m in components],axis=0)
    report=temperature_gate(f,prediction,f.temperature_both,gate);diagnostics={}
    for name in [simple,*ensembles]:
        v=vectors[name] if name in vectors else vector(name);ice=physical_ice(f,v);retention,events=event_retention(f,ice,f.physical_both)
        diagnostics[name]=dict(date_sensitivity=block_sensitivity(f,v,f.temperature_both),ice_if_new_temperature_used=runtime_daily(f,ice)[0],event_retention=retention)
    classifications={}
    for study in ['thermal_classification_20261024_v1','terrain_classification_20261024_v1']:
        result=read(PRIVATE/study/'summary.json');assert not any(r['eligible'] for r in result['reports'].values()),'New eligible icing method requires implementation review'
        classifications[study]=dict(reports=result['reports'],summary_sha256=sha(PRIVATE/study/'summary.json'))
    proposal=dict(status='selection_pending_model_audits',selected=chosen,simpler_reference=simple,temperature_report=report,
        components=[dict(name=n,folder=folders[n].relative_to(ROOT).as_posix(),predictions_sha256=sha(folders[n]/'predictions.parquet')) for n in components],
        weights=[1/len(components)]*len(components),icing_policy='preserve_v2',last_capacity_relative_improvement=last_gain,
        asos_geometry_relative_gap=asos/target-1,seed_mae={n:reports[n]['regression']['pooled']['mae'] for n in ensembles['asos_solar1200_three_seed_mean']},
        comparison_plan_sha256=sha(rulepath),loss_pair_plan_sha256=sha(ROOT/'config/solar_loss_pair_20261024.json'),protected_outcomes_used=False,new_independent_assessment=False)
    a.output.mkdir(parents=True);pd.DataFrame(registry).sort_values('mae').to_csv(a.output/'regression_registry.csv',index=False,encoding='utf-8-sig')
    write(a.output/'selection_proposal.json',proposal);write(a.output/'summary.json',dict(status='all_declared_comparisons_completed',
        regression_candidates=len(registry),regression_reports=reports,fixed_blend_reports=blends,earlier_declared_blend_reports=earlier_blends,diagnostics=diagnostics,
        classification=classifications,selection=proposal,baseline_sha256=sha(basepath),protected_outcomes_used=False,new_independent_assessment=False))
    assert preservation()==frozen
    print(json.dumps(dict(selected=chosen,mae=report['regression']['pooled']['mae'],last_capacity_gain=last_gain,seed_mae=proposal['seed_mae']),indent=2),flush=True)


if __name__=='__main__':main()
