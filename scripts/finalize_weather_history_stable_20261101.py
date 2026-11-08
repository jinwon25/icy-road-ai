"""실제12적합과 재사용 기준모형을 잘못 센 종료 검사만 교정해 완료 결과를 보존한다."""
from pathlib import Path
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from scripts.evaluate_weather_history_spatial_20261101 import report
from scripts.evaluate_weather_space_time import sensitivity
from src.data_source import sha256_file as sha


def verify_training_sources(out):
    recorded=read(out/'plan.json');fixes=[]
    for name,digest in recorded['signatures'].items():
        current=ROOT/name
        if sha(current)==digest:continue
        assert name=='scripts/evaluate_weather_history_stable_20261101.py',name
        archived=out/'source_before_fit_counter_fix.py';assert sha(archived)==digest
        before=archived.read_text('utf-8')
        after=before.replace('16+4회','8+4회').replace("'/20'","'/12'").replace('len(fits)==20','len(fits)==12')
        assert after==current.read_text('utf-8'),'Only three fit-counter text changes are allowed'
        fixes.append(dict(path=name,original_sha256=digest,fixed_sha256=sha(current),
            snapshot=archived.name,scope='docstring, progress denominator and final count assertion only; no training changes'))
    return fixes


def main():
    config=ROOT/'config/weather_humidity_stable_20261101.json';plan=read(config);out=ROOT/plan['output']
    if (out/'summary.json').exists():raise FileExistsError('Preserve completed stable study')
    fixes=verify_training_sources(out);fits=[];reports={}
    proof=read(out/'numeric_equivalence.json');assert sha(out/'features.parquet')==proof['feature_sha256']
    for mode in ['joint','spatial']:
        folder=out/mode
        for path in sorted(folder.glob('*.json')):
            record=read(path)
            assert record['mode']==mode
            assert sha(path.with_suffix('.joblib'))==record['model_sha256']
            assert sha(path.with_suffix('.npy'))==record['prediction_sha256']
            fits.append(record)
        p=pd.read_parquet(folder/'predictions.parquet')
        assert not p.duplicated(['station','time']).any()
        metrics={c:report(p,c) for c in ['asos','aws_fallback','instant_residual','stable_history']}
        boot=sensitivity(p,'stable_history','instant_residual',plan['bootstrap'])
        c=metrics['stable_history'];b=metrics['instant_residual'];g=plan['gates']
        gates=dict(pooled=c['pooled']['mae']<=b['pooled']['mae']*(1-g['minimum_mae_reduction']),
            both_winters=all(c['winters'][y]['mae']<=v['mae']*g['maximum_winter_mae_ratio'] for y,v in b['winters'].items()),
            every_region=all(c['regions'][k]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for k,v in b['regions'].items()),
            cold=c['cold']['mae']<=b['cold']['mae']*g['maximum_cold_mae_ratio'],date_sensitivity=boot['quantiles'][2]<0)
        reports[mode]=dict(metrics=metrics,bootstrap=boot,gates=gates,primary_success=all(gates.values()))
    assert len(fits)==12 and sum(r['mode']=='joint' for r in fits)==8
    assert verify_preserved()==read(out/'plan.json')['preservation']
    write(out/'fit_counter_fix.json',dict(at_utc=now(),verified_changes=fixes,actual_new_fits=12,
        reference_models_reused=True,finalizer_sha256=sha(Path(__file__))))
    write(out/'summary.json',dict(status='stable_humidity_history_complete',reports=reports,fits=fits,
        primary_success=all(r['primary_success'] for r in reports.values()),
        preservation=read(out/'plan.json')['preservation'],production_model_changed=False,new_independent_assessment=False,
        fit_counter_fix=fixes,files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print('FINALIZED',len(fits),{k:v['gates'] for k,v in reports.items()},flush=True)


if __name__=='__main__':main()
