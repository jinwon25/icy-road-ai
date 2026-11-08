"""현재 결과와 계측 계획을 두 제출 ZIP으로 묶고 압축 해제 후 실제 실행을 확인한다."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys,shutil,zipfile,subprocess,os
import numpy as np,pandas as pd,geopandas as gpd,fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.kma_rwis_download import load_auth_key
from scripts.package_review_v8 import archive
from scripts.review_submission_bundle import verify_directory
from scripts.check_markdown import inspect_documents
from scripts.evaluate_objective_icing import verify_preserved

P=ROOT/'outputs/private';W=P/'evening_refinement_20261106';B=W/'icy_road_model';D=W/'icy_road_documents'
CURRENT=P/'competition_submission';TEAM='로드투인사이트'
NAMES={'documents':TEAM+'_문서자료.zip','model':TEAM+'_모델자료.zip'}
FOLDERS={'documents':TEAM+'_문서자료','model':TEAM+'_모델자료'}

def read(p):return json.loads(p.read_text('utf8'))
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
def copy(a,b):b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a,b)

def manifest(folder,channel):
    original=W/'manifests_before_final_packaging'/(channel+'.json')
    if not original.exists():copy(folder/'manifest.json',original)
    files={p.relative_to(folder).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p))
        for p in folder.rglob('*') if p.is_file() and p!=folder/'manifest.json'
        and '__pycache__' not in p.parts and p.suffix!='.pyc'
        and p.relative_to(folder).parts[0]!='local_review'}
    value=dict(package_label='competition_submission',channel=channel,status='verified_local_submission',
        current_report='report/analysis_report.pdf',files=files,competition_submitted=False)
    if channel=='model':value.update(current_notebook='notebooks/analysis.ipynb',current_explorer='index.html',current_demo='demo/index.html')
    put(folder/'manifest.json',value);verify_directory(folder)

def main():
    assert not (W/'submission_receipt.json').exists()
    baseline=read(W/'baseline_receipt.json')
    for kind,name in NAMES.items():assert sha(CURRENT/name)==baseline['archives'][kind]['sha256']
    for folder in ['field_browser_final','media_review_final','browser_review_final']:
        r=read(W/folder/'receipt.json');assert r['status']=='passed' and r['visual_review']=='passed'
    experiments=read(P/'fixed_temperature_icing_20261106/summary.json')
    assert not experiments['passed_candidates'] and not experiments['production_model_changed']
    assert read(B/'local_review/fixed_rule_reproduction/receipt.json')['status']=='exact_fixed_rule_metrics_reproduced'
    previous=read(CURRENT/'icy_road_model/manifest.json')['files']
    allowed={'README.md','AI_USAGE.md','index.html','maps/sections.html','assets/inspection_template.txt','summary.json','technical/judging_evidence.json'}
    changed=[];same=0
    for name,item in previous.items():
        if sha(B/name)==item['sha256']:same+=1
        else:
            assert name in allowed or name.startswith(('demo/','validation/')),name
            changed.append(name)
    print('CHECK preserved',same,'files; final display files',len(changed),flush=True)
    preserved=verify_preserved()
    assert sha(B/'report/analysis_report.pdf')==previous['report/analysis_report.pdf']['sha256']
    doc=fitz.open(B/'report/analysis_report.pdf');assert len(doc)==13 and doc.metadata['author']==TEAM
    field_pdf=fitz.open(B/'results/field/field_measurement_plan.pdf');assert len(field_pdf)==2 and field_pdf.metadata['author']==TEAM
    assert (B/'results/field/field_measurement_plan.pdf').read_bytes()==(D/'report/field_measurement_plan.pdf').read_bytes()
    assert sha(B/'maps/sections.html')==sha(B/'local_review/sections_final.html')
    media=read(W/'media_review_final/receipt.json')
    assert sha(B/'demo/model_demo.webm')==media['video_sha256'] and media['decoded_frames']==12
    field=read(W/'field_browser_final/receipt.json')
    for name,digest in field['source_sha256'].items():assert sha(B/name)==digest,name
    for name,digest in media['source_files'].items():assert sha(B/name)==digest,name
    for source,name in [('browser_review_final','section_browser.json'),('media_review_final','media_browser.json'),('field_browser_final','field_browser.json')]:
        copy(W/source/'receipt.json',B/'validation'/name)
    copy(B/'local_review/fixed_rule_reproduction/receipt.json',B/'validation/fixed_temperature_rule_reproduction.json')
    put(B/'validation/media_visual_review.json',dict(status='passed',video_sha256=media['video_sha256'],decoded_frames=12,seconds=media['video_metadata']['duration'],team_name=TEAM))
    summary=read(B/'summary.json');summary['status']='verified_offline_analysis'
    summary['files']={name:sha(B/name) for name in ['index.html','viewer_data.json.gz','maps/sections.html','results/field/index.html','demo/model_demo.webm']}
    put(B/'summary.json',summary)
    facts=read(B/'technical/judging_evidence.json')
    facts['field_comparison_plan']=read(B/'results/field/summary.json')
    facts['fixed_temperature_rules']=dict(new_model_fits=0,common_rows=309928,observed_ice=6687,promoted=0,
        report='results/evaluation/fixed_temperature_rule_review/summary.json')
    put(B/'technical/judging_evidence.json',facts)
    key=load_auth_key(ROOT/'secret.env').encode();compiled=0
    for folder in [B,D]:
        names=[p.relative_to(folder).as_posix() for p in folder.rglob('*.md') if 'local_review' not in p.relative_to(folder).parts]
        errors=inspect_documents(folder,names);assert not errors,errors
        for path in folder.rglob('*'):
            if not path.is_file() or 'local_review' in path.relative_to(folder).parts or '__pycache__' in path.parts:continue
            assert path.suffix.lower() not in ['.env','.key','.pem','.curl'] and '.secret' not in path.name,path.name
            with path.open('rb') as stream:
                tail=b''
                while block:=stream.read(1024*1024):
                    content=tail+block;assert key not in content,'Credential in package file'
                    tail=content[-max(512,len(key)):]
            if path.suffix=='.py':compile(path.read_text('utf-8-sig'),str(path),'exec');compiled+=1
    checks=read(B/'validation/delivery_checks.json')
    checks.update(status='passed',team_name=TEAM,main_report_pages=13,field_plan_pages=2,
        field_comparison_candidates=2,actual_field_measurements=0,field_browser_viewports=3,
        field_record_csv_rows=4,record_save_restore_passed=True,invalid_record_import_atomic=True,
        fixed_temperature_candidates_promoted=0,new_model_fits=0,fixed_rule_metric_rows_reproduced=24,
        python_files_compiled=compiled,original_model_files_unchanged=same,
        final_display_files_changed=changed,credential_scan_passed=True,competition_submitted=False)
    put(B/'validation/delivery_checks.json',checks);put(W/'delivery_checks.json',checks)
    for folder,channel in [(B,'model'),(D,'documents')]:
        manifest(folder,channel)
        value=read(folder/'manifest.json');value['team_name']=TEAM
        if channel=='model':value['current_field_plan']='results/field/index.html'
        put(folder/'manifest.json',value);verify_directory(folder)
    print('CHECK manifests and credentials passed; archiving',flush=True)
    archives={kind:archive(folder,W/NAMES[kind],FOLDERS[kind]) for kind,folder in [('documents',D),('model',B)]}
    extracted=W/'extracted_submission_check';extracted.mkdir()
    for kind in ['documents','model']:
        with zipfile.ZipFile(W/NAMES[kind]) as z:
            assert {n.split('/')[0] for n in z.namelist()}=={FOLDERS[kind]}
            assert not any('local_review' in n or '.secret' in n or n.endswith(('.env','.key','.pem','.curl')) for n in z.namelist())
            z.extractall(extracted)
        verify_directory(extracted/FOLDERS[kind])
    model=extracted/FOLDERS['model'];env=dict(os.environ)
    env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    def run(args):
        r=subprocess.run([sys.executable,'-X','utf8',*args],cwd=model,env=env,capture_output=True,text=True,encoding='utf8',timeout=240)
        assert r.returncode==0,r.stdout+r.stderr
        return r.stdout
    run(['code/predict.py','--input','data/weather_example.csv','--output','local_review/archive_prediction.csv','--output-start','2024-12-15','--output-end','2024-12-16'])
    options=dict(dtype={'station':str},float_precision='round_trip')
    pd.testing.assert_frame_equal(pd.read_csv(model/'local_review/archive_prediction.csv',**options),pd.read_csv(model/'data/example_predictions.csv',**options),check_exact=True)
    run(['code/build_field_plan.py','--output','local_review/rebuilt_field'])
    for name in ['comparison_candidates.csv','measurement_protocol.csv','field_cases.json','index.html','summary.json']:
        assert sha(model/'local_review/rebuilt_field'/name)==sha(model/'results/field'/name),name
    lhs=gpd.read_file(model/'local_review/rebuilt_field/measurement_plan.gpkg',engine='pyogrio')
    rhs=gpd.read_file(model/'results/field/measurement_plan.gpkg',engine='pyogrio')
    pd.testing.assert_frame_equal(lhs.drop(columns='geometry'),rhs.drop(columns='geometry'),check_exact=True)
    assert lhs.crs==rhs.crs and all(a.equals_exact(b,0) for a,b in zip(lhs.geometry,rhs.geometry))
    run(['code/compare_fixed_temperature_rules.py','--output','local_review/fixed_rule_comparison'])
    assert verify_preserved()==preserved
    receipt=dict(status='two_channel_archives_verified',team_name=TEAM,archives=archives,archive_filenames=NAMES,archive_root_folders=FOLDERS,
        report_pages=13,field_plan_pages=2,demo_seconds=media['video_metadata']['duration'],checks=checks,
        extracted_archives_verified=True,extracted_model_inference_rows_exact=144,
        extracted_field_comparison_reproduced=True,extracted_fixed_rule_metrics_reproduced=True,
        core_models_training_and_required_prediction_values_unchanged=True,competition_submitted=False,
        at_utc=datetime.now(timezone.utc).isoformat())
    put(W/'submission_receipt.json',receipt)
    print(json.dumps(dict(status=receipt['status'],archives=archives,demo_seconds=receipt['demo_seconds']),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
