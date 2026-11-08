"""추가 결빙 연구의 학습 범위·실행·공식 지표·보호 봉인과 제출물 보존을 검산한다."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys,argparse
import numpy as np
import pandas as pd
import joblib
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.icing_precision_20261106 import features,binary_prediction
from src.icing_local_context_20261106 import features as local_features
from src.icing_snow_age_20261106 import snow_growth_history
from src.submission_runtime import FEATURES,WATER,infer
from src.data_source import sha256_file as sha
from scripts.evaluate_icing_precision_20261106 import read,write
from scripts.evaluate_official_icing_upgrade_20261106 import independent
from scripts.evaluate_objective_icing import verify_preserved
FORBIDDEN={'12410','33411','23402','33402','33406','12213','23411'}


def metric_check(frame,name,reference):
    checks=0
    for minimum in [1,144]:
        actual=independent(frame,frame[name].to_numpy(float),minimum)
        for key,value in actual.items():
            expected=reference[str(minimum)][key]
            if value is None:assert expected is None
            else:np.testing.assert_allclose(value,expected,atol=1e-12,rtol=0)
            checks+=1
    return checks


def classifier_audit(model_dir,comparison_dir,feature_fn,expected_new):
    plan=read(model_dir/'plan.json');summary=read(comparison_dir/'summary.json')
    for path,digest in plan['signatures'].items():assert sha(ROOT/path)==digest,path
    f=pd.read_parquet(ROOT/plan['settings']['source']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&FORBIDDEN
    specs={v['name']:v for v in plan['settings']['models']}
    x={kind:feature_fn(f,kind) for kind in sorted({v['features'] for v in specs.values()})}
    replay=0;new=0
    for fit in summary['fits']:
        held=f.group.isin(fit['excluded']).to_numpy()
        assert not set(fit['training_stations'])&set(f.loc[held,'station'])
        assert not set(fit['training_stations'])&FORBIDDEN
        assert len(fit['excluded']) in [1,2]
        stem='__'.join(fit['excluded'])+'__'+fit['name']
        assert sha(model_dir/(stem+'.joblib'))==fit['model_sha256']
        assert sha(model_dir/(stem+'.parquet'))==fit['scores_sha256']
        if fit.get('reused',False):continue
        new+=1
        scores=pd.read_parquet(model_dir/(stem+'.parquet'));query=f.loc[held]
        pd.testing.assert_frame_equal(query[['station','time']].reset_index(drop=True),scores[['station','time']])
        positions=np.linspace(0,len(query)-1,min(17,len(query)),dtype=int)
        model=joblib.load(model_dir/(stem+'.joblib'))
        label=3 if fit.get('target')=='state' else 1
        with threadpool_limits(limits=2):
            pred=model.predict_proba(x[specs[fit['name']]['features']].loc[held].iloc[positions])[:,list(model.classes_).index(label)]
        np.testing.assert_array_equal(pred,scores.score.iloc[positions].to_numpy(float))
        replay+=len(positions)
    assert new==expected_new
    q=pd.read_parquet(comparison_dir/'predictions.parquet')
    assert sha(comparison_dir/'predictions.parquet')==summary['predictions_sha256']
    assert not set(q.station)&FORBIDDEN
    checks=sum(metric_check(q,name,report) for name,report in summary['reports'].items())
    for decision in read(model_dir/'selection_seal.json')['decisions']:
        subset=q.loc[q.group.eq(decision['held'])]
        for track,spec in decision['choices'].items():
            actual=np.where(subset.available,subset.asos_air_temp.le(0),np.nan) if spec['name']=='asos_zero' else binary_prediction(subset,subset[spec['name']],spec['threshold'])
            np.testing.assert_array_equal(actual,subset[track+'_track'])
    return new,replay,checks



def cached_classifier_audit(name,model_dir,comparison_dir,feature_fn,expected_new):
    out=ROOT/'outputs/private/icing_precision_review_20261106'
    out.mkdir(exist_ok=True)
    target=out/(name+'_audit.json')
    fingerprint=dict(audit_code_sha256=sha(Path(__file__)),model_plan_sha256=sha(model_dir/'plan.json'),
        comparison_summary_sha256=sha(comparison_dir/'summary.json'),selection_sha256=sha(model_dir/'selection_seal.json'))
    summary=read(comparison_dir/'summary.json')
    for path,digest in read(model_dir/'plan.json')['signatures'].items():
        assert sha(ROOT/path)==digest,path
    for fit in summary['fits']:
        stem='__'.join(fit['excluded'])+'__'+fit['name']
        assert sha(model_dir/(stem+'.joblib'))==fit['model_sha256']
        assert sha(model_dir/(stem+'.parquet'))==fit['scores_sha256']
    assert sha(comparison_dir/'predictions.parquet')==summary['predictions_sha256']
    if target.exists():
        cached=read(target)
        assert cached['fingerprint']==fingerprint
        return cached['new_models'],cached['replayed_rows'],cached['metric_checks']
    n,r,c=classifier_audit(model_dir,comparison_dir,feature_fn,expected_new)
    write(target,dict(status='passed',fingerprint=fingerprint,new_models=n,replayed_rows=r,metric_checks=c))
    return n,r,c

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--part',choices=['all','process','state','local'],default='all');args=ap.parse_args()
    p=ROOT/'outputs/private';out=p/'icing_precision_review_20261106';out.mkdir(exist_ok=True)
    target=out/'independent_audit.json'
    if target.exists():raise FileExistsError('Preserve completed audit')
    preserved=verify_preserved();new_models=replays=checks=0;receipts={}
    for name,models,result,func,count in [
        ('process','icing_precision_20261106','icing_precision_comparison_20261106',features,40),
        ('state','icing_multistate_20261106','icing_multistate_comparison_20261106',features,20),
        ('local','icing_local_context_20261106','icing_local_context_20261106',local_features,20)]:
        if args.part!='all' and args.part!=name:continue
        n,r,c=cached_classifier_audit(name,p/models,p/result,func,count)
        new_models+=n;replays+=r;checks+=c
        receipts[name]=dict(new_models=n,replayed_rows=r,metric_checks=c,summary_sha256=sha(p/result/'summary.json'))
        print('CLASSIFIER_AUDIT',name,n,r,c,flush=True)
    if args.part!='all':return
    b=p/'icing_snow_age_20261106_checked';t=read(b/'summary.json');freeze=read(b/'plan.json')
    for path,digest in freeze['signatures'].items():assert sha(ROOT/path)==digest,path
    source=pd.read_parquet(ROOT/freeze['settings']['weather_source'],columns=['station','time','asos_snow_cm','asos_new_snow3h']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(source.station)&FORBIDDEN
    saved=pd.read_parquet(b/'history.parquet');actual=snow_growth_history(source)
    pd.testing.assert_frame_equal(saved[actual.columns],actual)
    f=pd.read_parquet(ROOT/freeze['settings']['training_source'])
    context=pd.read_parquet(ROOT/freeze['settings']['context_source'],columns=['station','time',*WATER])
    added=[c for c in WATER if c not in f]
    f=f.merge(context[['station','time',*added]],on=['station','time'],validate='one_to_one')
    pair_names=set()
    for fit in t['new_fits']:
        held=set(f.loc[f.group.isin(fit['excluded']),'station'])
        assert not set(fit['training_stations'])&held
        assert not set(fit['training_stations'])&FORBIDDEN
        assert len(fit['excluded'])==2
        stem='__'.join(fit['excluded'])
        assert sha(b/(stem+'__'+fit['kind']+'.joblib'))==fit['model_sha256']
        pair_names.add(stem)
    assert len(t['new_fits'])==12 and len(pair_names)==6
    temp_replays=0
    for stem in pair_names:
        expected=pd.read_parquet(b/(stem+'__predictions.parquet'))
        selected=expected.iloc[np.linspace(0,len(expected)-1,17,dtype=int)]
        weather=selected[['station','time']].merge(f[list(dict.fromkeys(['station','time',*FEATURES,*WATER]))],on=['station','time'],validate='one_to_one')
        models=[joblib.load(b/(stem+'__'+label+'.joblib')) for label in ['mse','mae']]
        replay=infer(weather,models)
        np.testing.assert_array_equal(replay.predicted_ice.to_numpy(float,na_value=np.nan),selected.baseline.to_numpy(float))
        temp_replays+=len(selected)
    q=pd.read_parquet(b/'predictions.parquet')
    assert sha(b/'predictions.parquet')==t['predictions_sha256']
    checks+=sum(metric_check(q,name,report) for name,report in t['reports'].items())
    for policy in ['snow_growth_6h','snow_growth_24h','snow_growth_72h']:
        assert np.array_equal(np.isfinite(q[policy]),np.isfinite(q.baseline))
        assert np.all(q.loc[q.baseline.eq(0),policy].eq(0))
        assert np.all(q.loc[q[policy].eq(1),'baseline'].eq(1))
    for decision in t['decisions']:
        subset=q.loc[q.group.eq(decision['held'])]
        np.testing.assert_array_equal(subset.nested,subset[decision['candidate']])
    new_models+=12
    # 보호 평가 봉인 파일의 본문은 해시로만 확인한다.
    seal_path=p/'final_selection_20261106_v14/selection_seal.json';final_seal=read(seal_path)
    for path,digest in final_seal['source_signatures'].items():assert sha(ROOT/path)==digest,path
    package=p/'competition_submission';receipt=read(package/'submission_receipt.json')
    for kind,filename in [('documents','icy_road_documents.zip'),('model','icy_road_model.zip')]:
        assert sha(package/filename)==receipt['archives'][kind]['sha256'],filename
        assert (package/filename).stat().st_size==receipt['archives'][kind]['bytes']
    assert verify_preserved()==preserved
    write(target,dict(status='passed',at_utc=datetime.now(timezone.utc).isoformat(),new_model_fits=new_models,
        replayed_classifier_rows=replays,replayed_temperature_rows=temp_replays,independent_metric_checks=checks,
        classifier_audits=receipts,snow_age_summary_sha256=sha(b/'summary.json'),
        protected_and_external_stations_excluded=True,final_seal_signatures=len(final_seal['source_signatures']),
        production_archives_unchanged=True,production_model_changed=False,
        diagnosis_summary_sha256=sha(p/'icing_precision_diagnosis_20261106/summary.json'),competition_submitted=False))
    print('PASS',new_models,'new fits,',checks,'metric checks, production archives unchanged',flush=True)


if __name__=='__main__':main()
