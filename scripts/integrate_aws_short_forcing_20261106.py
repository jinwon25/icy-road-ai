"""검토 가능한 실패 근거와 현재 열람 안내를 제출 작업본에 연결한다."""
from pathlib import Path
import json,sys,shutil
from datetime import datetime,timezone,timedelta
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
P=ROOT/'outputs/private';W=P/'late_research_design_20261106';B=W/'icy_road_model';D=W/'icy_road_documents';E=P/'aws_short_forcing_icing_20261106'
def put(p,v):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
def read(p):return json.loads(p.read_text('utf8'))
def main():
    result=read(E/'summary.json');audit=read(E/'audit.json');assert not result['promote']
    folder=B/'results/evaluation/aws_short_forcing_review';folder.mkdir()
    f=pd.read_parquet(E/'predictions.parquet',columns=['station','time','winter','group','ice','physical','asos_zero','candidate'])
    assert len(set(f.station))==9 and not set(f.station)&{'12410','33411','23402','33402','33406','12213','23411'}
    f.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
    rows=[]
    for name in ['physical','asos_zero','candidate']:
        r=result['reports'][name]
        for scope,report in [('all',r['1']),('strict144',r['144']),*r['winters'].items(),*r['regions'].items()]:
            rows.append(dict(method=name,scope=scope,**{k:report[k] for k in ['precision','recall','f1','tp','fp','fn']}))
    pd.DataFrame(rows).to_csv(folder/'comparison.csv',index=False)
    feasible=sum(int(pd.read_csv(p).track.eq('precision').sum()) for p in E.glob('*__selection.csv'))
    assert feasible==0
    compact=dict(status='short_forcing_candidate_not_promoted',source='https://arxiv.org/abs/2609.33528',source_type='preprint',
        scope='Nearby AWS cooling, thaw, drying and rain histories plus current ASOS. No observed pavement state or temperature; not future-onset prediction.',
        decay_minutes=[10,30,120],new_model_fits=20,threshold_searches=16,outer_regions=4,inner_pair_exclusions=6,
        common_valid_pairs=309928,guarded_precision_feasible_candidates=feasible,
        metrics={n:{k:r['1'][k] for k in ['precision','recall','f1']} for n,r in result['reports'].items()},
        decisions=result['decisions'],promotion_gates=result['promotion_gates'],promote=False,
        formula_audit={'status':audit['status'],'constant_cold_closed_form_max_error':audit['constant_cold_closed_form_max_error'],
            'missing_time_gap_resets':True,'station_isolation_exact':True,'model_reload_exact':20,
            'strict_past_perturbation_passed':read(E/'feature_checks.json')['strict_past_perturbation_passed']},
        saved_predictions_sha256=sha(folder/'predictions.parquet'),saved_comparison_sha256=sha(folder/'comparison.csv'),
        protected_outcomes_used=False,external_four_outcomes_used=False,new_independent_assessment=False,production_model_changed=False,
        reproduction_scope='code/analyze_aws_short_forcing_review.py recomputes metrics from included fixed out-of-fold predictions; it does not refit the experimental classifiers.')
    put(B/'technical/aws_short_forcing_review.json',compact);put(D/'data/aws_short_forcing_review.json',compact)
    shutil.copy2(folder/'comparison.csv',D/'data/aws_short_forcing_comparison.csv')

if __name__=='__main__':main()
