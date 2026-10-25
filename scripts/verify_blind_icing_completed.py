"""완료된 독립 평가의 원문→정규화, 요청 범위, 성공 조건을 읽기 전용으로 재검산한다."""
import argparse
from pathlib import Path
import sys
import json
import hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.blind_icing_validation import DEFAULT,PRIVATE,verify,read,write,transport_plans,now
from src.kma_rwis_download import daily_requests,parse_observations,exact_ten_minute_grid
from src.data_source import sha256_file as sha
from scripts.fresh_station_validation import old_freezes
from scripts.audit_icing_transition import independent_metrics,independent_events
from src.rwis_response_quality import quarantine_duplicates


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();dest=args.output.resolve()
    if dest.exists() or not dest.is_relative_to(PRIVATE.resolve()):raise ValueError('New private receipt required')
    out=DEFAULT;seal=verify(out);plan=read(out/'plan.json');summary=read(out/'summary.json');audit=read(out/'result_audit.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(out/'summary.json')
    manifest=read(out/'download_manifest.json');assert manifest['status']=='complete'
    expected={}
    for p in transport_plans(plan):
        for station,start,end in daily_requests(p,p['development_start_kst'],p['development_end_kst'],window_minutes=p['window_minutes']):
            expected[f'{station}_{start:%Y%m%d%H%M}']=(station,start,end)
    assert set(expected)==set(manifest['records']) and len(expected)==960
    raw_rows=0;response_count=0;conflict_keys=0;conflict_rows=0;quality_responses=0
    for n,(key,(station,start,end)) in enumerate(expected.items(),1):
        record=manifest['records'][key];assert record['station']==station and pd.Timestamp(record['start_kst'])==start and pd.Timestamp(record['end_kst'])==end
        parts=[];intervals=[]
        for r in record['transport']:
            path=out/'transport'/r['transport_cache_path'];assert sha(path)==r['transport_response_sha256']
            if 'quality_receipt' in r:
                qr=out/r['quality_receipt'];assert sha(qr)==r['quality_receipt_sha256'];quality=read(qr)
                original=out/quality['raw_path'];assert sha(original)==quality['raw_sha256']
                canonical,details=quarantine_duplicates(original.read_text('utf-8'),station)
                assert details==quality['report'] and canonical==path.read_text('utf-8')
                assert hashlib.sha256(canonical.encode()).hexdigest()==quality['canonical_text_sha256']
                conflict_keys+=details['conflicting_keys'];conflict_rows+=details['conflicting_rows_removed'];quality_responses+=1
            a,b=pd.Timestamp(r['start_kst']),pd.Timestamp(r['end_kst']);assert start<=a<=b<=end
            g=parse_observations(path.read_text('utf-8'),station,a,b);parts.append(g);intervals.append((a,b));raw_rows+=len(g);response_count+=1
        intervals=sorted(intervals);assert intervals[0][0]==start and intervals[-1][1]==end
        assert all(a[1]+pd.Timedelta(minutes=1)==b[0] for a,b in zip(intervals,intervals[1:]))
        reconstructed=exact_ten_minute_grid(pd.concat(parts,ignore_index=True)).reset_index(drop=True)
        path=out/'observations'/(key+'.parquet');assert sha(path)==record['sha256'];stored=pd.read_parquet(path).reset_index(drop=True)
        pd.testing.assert_frame_equal(reconstructed,stored,check_dtype=False)
        if n%120==0:print('RAW AUDIT',n,'/ 960',flush=True)
    f=pd.read_parquet(out/'evaluation.parquet');primary=plan['primary_candidate'];pop=plan['new_stations'];evidence=plan['evidence_minimum']
    b=independent_metrics(f,f.asos_zero);c=independent_metrics(f,f[primary]);events=independent_events(f,f[primary],f.asos_zero)
    counts=f.assign(valid=f.ice.isin([0,1])&f.available).groupby(['station','winter']).agg(valid=('valid','sum'),rows=('time','size'))
    positive=f.loc[f.ice.eq(1)&f.available].station.nunique();points=pd.read_csv(out/'points.csv',dtype={'station':str}).set_index('station')
    coord=True
    for (station,_),g in f.groupby(['station','winter']):
        for col in ['lat','lon']:
            delta=(g[col]-points.loc[station,col]).abs();coord&=bool(delta.notna().any() and delta.max()<=.01)
    gates=dict(valid_sites=int(counts.groupby('station').valid.sum().gt(0).sum())>=evidence['valid_sites'],
        coverage=bool((counts.valid/counts.rows).ge(evidence['coverage_per_site_winter']).all()),positive_sites=positive>=evidence['positive_sites'],
        positive_events=events['observed_events']>=evidence['positive_events'],coordinate_consistency=coord,
        f1_improves=c['f1_fixed_population']>=1.01*b['f1_fixed_population'] and c['f1_fixed_population']>b['f1_fixed_population'],
        each_winter=all(independent_metrics(g,g[primary])['f1_fixed_population']>=independent_metrics(g,g.asos_zero)['f1_fixed_population'] for _,g in f.groupby('winter')),
        each_site=all(independent_metrics(g,g[primary])['f1_fixed_population']>=independent_metrics(g,g.asos_zero)['f1_fixed_population'] for _,g in f.groupby('station')),
        no_lost_events=events['lost_events']==0)
    for m in ['precision','recall']:
        k=m+'_available_station_mean';gates[m+'_noninferior']=b[k] is not None and c[k] is not None and c[k]>=b[k]
    assert gates==summary['primary_gates'] and all(gates.values())==summary['primary_success']
    timing=[json.loads(line) for line in (out/'global_request_timing.jsonl').read_text('utf-8').splitlines()]
    current=[t for t in timing if t.get('scheduler_version')==2]
    intervals=[b['monotonic']-a['monotonic'] for a,b in zip(current,current[1:])];assert min(intervals)>=1.2
    assert sha(out/'transport_controller_v1.py')==read(out/'transport_amendment.json')['code_sha256']
    assert sha(out/'transport_controller_v2.py')==read(out/'transport_amendment_v2.json')['code_sha256']
    assert sha(out/'transport_controller_v3.py')==read(out/'transport_amendment_v3.json')['code_sha256']
    assert sha(ROOT/'scripts/resume_blind_icing_transport.py')==read(out/'transport_amendment_v4.json')['code_sha256']
    assert sha(ROOT/'src/rwis_response_quality.py')==read(out/'label_quality_amendment.json')['quality_code_sha256']
    assert read(out/'label_quality_amendment.json')['at_utc']<summary['evaluated_at_utc']
    zip_path=PRIVATE/'submission_candidate_20261025_v5.zip';zip_digest=sha(zip_path)
    assert zip_digest=='0dcc1f5e2984ec3544b320f2bcec95ee4054a557dd2b320832de981c9d63e8e4'
    write(dest,dict(status='completed_evaluation_verified_from_raw_responses',at_utc=now(),daily_windows=960,
        response_files=response_count,raw_valid_minute_rows=raw_rows,primary_gate_checks=len(gates),
        conflict_quarantined_keys=conflict_keys,conflict_quarantined_rows=conflict_rows,quality_affected_responses=quality_responses,
        current_scheduler_requests=len(current),current_minimum_interval_seconds=min(intervals),
        original_seal_sha256=sha(out/'prediction_seal.json'),summary_sha256=sha(out/'summary.json'),
        result_audit_sha256=sha(out/'result_audit.json'),frozen_counts=list(old_freezes()),v5_zip_sha256=zip_digest,
        code_sha256=sha(Path(__file__)),new_training_or_model_selection=False))
    print('FULL RAW AND GATE AUDIT PASSED',flush=True)


if __name__=='__main__':main()
