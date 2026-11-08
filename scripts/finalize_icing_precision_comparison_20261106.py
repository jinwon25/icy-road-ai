"""유효 입력 범위가 다른 기존모델을 공통 마스크로 맞춰 봉인된 선택 결과를 집계한다."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,argparse
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.icing_precision_20261106 import binary_prediction
from src.data_source import sha256_file as sha
from scripts.evaluate_icing_precision_20261106 import read,write,now
from scripts.evaluate_icing_snow_age_20261106 import reports_for
from scripts.evaluate_official_icing_upgrade_20261106 import block
from scripts.evaluate_objective_icing import verify_preserved


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--kind',choices=['binary','state'],required=True);args=ap.parse_args()
    source_name='icing_precision_20261106' if args.kind=='binary' else 'icing_multistate_20261106'
    out_name='icing_precision_comparison_20261106' if args.kind=='binary' else 'icing_multistate_comparison_20261106'
    source=ROOT/'outputs/private'/source_name;out=ROOT/'outputs/private'/out_name
    if out.exists():raise FileExistsError('Preserve completed comparison')
    plan=read(source/'plan.json');settings=plan['settings']
    for path,digest in plan['signatures'].items():assert sha(ROOT/path)==digest,path
    selection=read(source/'selection_seal.json')
    assert selection['outer_metrics_computed'] is False
    preserved=verify_preserved()
    f=pd.read_parquet(ROOT/settings['source']).sort_values(['station','time']).reset_index(drop=True)
    blocked=set(settings['blocked_stations']);assert not set(f.station)&blocked
    parts=[]
    for decision in selection['decisions']:
        held=decision['held']
        q=f.loc[f.group.eq(held),['station','time','group','winter','ice','available','asos_air_temp']].copy().reset_index(drop=True)
        for spec in settings['models']:
            saved=pd.read_parquet(source/(held+'__'+spec['name']+'.parquet'))
            pd.testing.assert_frame_equal(saved[['station','time']],q[['station','time']])
            q[spec['name']]=saved.score.to_numpy(float)
        q['asos_zero']=np.where(q.available,q.asos_air_temp.le(0),np.nan)
        for track,spec in decision['choices'].items():
            q[track+'_track']=q.asos_zero if spec['name']=='asos_zero' else binary_prediction(q,q[spec['name']],spec['threshold'])
        parts.append(q)
    result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    reference=pd.read_parquet(ROOT/settings['reference'],columns=['station','time','ice','physical_both'])
    result=result.merge(reference,on=['station','time'],validate='one_to_one',suffixes=['','_reference'])
    np.testing.assert_array_equal(result.ice,result.ice_reference)
    before=result.physical_both.copy()
    assert np.all(~result.available|np.isfinite(before))
    difference=np.isfinite(before)&~result.available
    delta=dict(rows=int(difference.sum()),observed_ice=int(result.loc[difference,'ice'].eq(1).sum()),
               originally_alerted_rows=int(before.loc[difference].eq(1).sum()),
               stations={str(k):int(v) for k,v in result.loc[difference].groupby('station').size().items()})
    result['physical_both']=before.where(result.available)
    result['baseline']=result.physical_both
    result=result.drop(columns='ice_reference')
    tracks=list(selection['decisions'][0]['choices'])
    names=['physical_both','asos_zero',*[t+'_track' for t in tracks]]
    for name in names:assert np.array_equal(np.isfinite(result[name]),result.available)
    out.mkdir()
    write(out/'plan.json',dict(at_utc=now(),original_source=source.relative_to(ROOT).as_posix(),
        original_plan_sha256=sha(source/'plan.json'),original_selection_sha256=sha(source/'selection_seal.json'),
        correction_sha256=sha(source/'evaluation_mask_addendum.json'),source_sha256=sha(Path(__file__)),
        settings=settings,common_mask_difference=delta,no_fitting_or_threshold_reselection=True))
    result.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    reports={};daily={}
    for name in names:
        r,d,e=reports_for(result,name);reports[name]=r;daily[name]=d
        d[1].to_csv(out/(name+'__daily_min1.csv'),index=False)
        d[144].to_csv(out/(name+'__daily_min144.csv'),index=False)
        e.to_csv(out/(name+'__events.csv'),index=False)
        print('REPORT',name,{k:r['1'][k] for k in ['precision','recall','f1']},flush=True)
    sensitivity={name:block(daily[name][1],daily['physical_both'][1],settings['seed']) for name in ['f1_track','precision_track']}
    c=reports['f1_track'];b=reports['physical_both'];a=reports['asos_zero'];g=settings['promotion_gate']
    gates=dict(precision=c['1']['precision']>=b['1']['precision']*(1+g['precision_relative_gain']),
               f1=c['1']['f1']>=max(b['1']['f1'],a['1']['f1'])*(1+g['f1_relative_gain_over_both_baselines']),
               strict144=c['144']['f1']>=max(b['144']['f1'],a['144']['f1']),
               recall=c['1']['recall']>=b['1']['recall']*g['recall_relative_to_production'],
               events=c['events']['lost_events']<=b['events']['candidate_detected']*g['maximum_lost_fraction_of_production_events'],
               winters=all(c['winters'][y]['f1']>=b['winters'][y]['f1'] for y in b['winters']),
               regions=all(c['regions'][v]['f1']>=b['regions'][v]['f1']*g['each_region_f1_relative_to_production'] for v in c['regions']),
               calendar_sensitivity=sensitivity['f1_track']['difference_percentiles'][0]>=0.)
    if args.kind=='state':
        gates['matched_binary']=c['1']['f1']>=reports['matched_binary_track']['1']['f1']*(1+g['matched_binary_relative_f1_gain'])
    fits=[]
    for path in sorted(source.glob('*__*.json')):
        record=read(path)
        if 'model_sha256' in record and 'scores_sha256' in record:fits.append(record)
    assert len(fits)==40
    assert verify_preserved()==preserved
    write(out/'summary.json',dict(status='common_input_precision_comparison_complete',at_utc=now(),kind=args.kind,
        reports=reports,decisions=selection['decisions'],fits=fits,
        new_fits=40 if args.kind=='binary' else sum(not r['reused'] for r in fits),
        promotion_gates=gates,promote=all(gates.values()),sensitivity=sensitivity,
        original_source=source.relative_to(ROOT).as_posix(),common_mask_difference=delta,
        predictions_sha256=sha(out/'predictions.parquet'),protected_outcomes_used=False,external_four_outcomes_used=False,
        new_independent_assessment=False,production_model_changed=False))
    print('COMPLETE',args.kind,gates,'promote',all(gates.values()),flush=True)


if __name__=='__main__':main()
