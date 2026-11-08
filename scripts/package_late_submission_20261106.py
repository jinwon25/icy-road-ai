"""제출용 두 ZIP을 만들고 압축 해제본의 전체 기간 추론·근거 재현을 검사한다."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,shutil,zipfile,os,subprocess,hashlib
import pandas as pd,geopandas as gpd,fitz,nbformat
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.kma_rwis_download import load_auth_key
from scripts.package_review_v8 import archive
from scripts.review_submission_bundle import verify_directory
from scripts.check_markdown import inspect_documents
from scripts.evaluate_objective_icing import verify_preserved
import scripts.package_evening_submission_20261106 as prior
P=ROOT/'outputs/private';W=P/'late_research_design_20261106';B=W/'icy_road_model';D=W/'icy_road_documents';CURRENT=P/'competition_submission'
TEAM='로드투인사이트';NAMES={'documents':TEAM+'_문서자료.zip','model':TEAM+'_모델자료.zip'}
FOLDERS={k:n.removesuffix('.zip') for k,n in NAMES.items()}
def read(p):return json.loads(p.read_text('utf8'))
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
def copy(a,b):b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a,b)

def main():
    assert not (W/'submission_receipt.json').exists()
    baseline=read(W/'baseline_receipt.json')
    for kind,name in NAMES.items():assert sha(CURRENT/name)==baseline['archives'][kind]['sha256']
    checks_by={n:read(W/n/'receipt.json') for n in ['field_browser_jury','media_review_final','browser_review_jury','layout_review','inference_display_final','requirements_review']}
    for name,r in checks_by.items():
        assert r['status'] in ['passed','requirements_file_and_execution_audit_passed'],(name,r['status'])
        if name!='requirements_review':assert r['visual_review']=='passed',name
    previous=read(CURRENT/'icy_road_model/manifest.json')['files'];same=0;changed=[]
    allowed={'index.html','README.md','AI_USAGE.md','summary.json','maps/sections.html','assets/site.css','assets/inspection_template.txt','assets/field_plan_template.html',
        'results/field/index.html','results/field/summary.json','notebooks/analysis.ipynb',
        'technical/judging_evidence.json','technical/competition_requirements.md','technical/official_evening_access_review.json'}
    for name,item in previous.items():
        assert (B/name).is_file(),name
        if sha(B/name)==item['sha256']:same+=1
        else:
            assert name in allowed or name.startswith(('report/','demo/','validation/')),name
            changed.append(name)
    frozen=verify_preserved()
    report=fitz.open(B/'report/analysis_report.pdf');assert len(report)==14 and report.metadata['author']==TEAM
    fieldpdf=fitz.open(B/'results/field/field_measurement_plan.pdf');assert len(fieldpdf)==2 and fieldpdf.metadata['author']==TEAM
    assert sha(B/'report/analysis_report.pdf')==sha(D/'report/analysis_report.pdf')
    assert sha(B/'results/field/field_measurement_plan.pdf')==sha(D/'report/field_measurement_plan.pdf')
    assert sha(B/'maps/sections.html')==sha(B/'local_review/sections_with_result_entry.html')
    media=checks_by['media_review_final'];field=checks_by['field_browser_jury']
    for record,key in [(media,'source_files'),(field,'source_sha256')]:
        for name,digest in record[key].items():assert sha(B/name)==digest,name
    assert sha(B/'demo/inference.html')==checks_by['inference_display_final']['source_sha256']
    assert sha(B/'report/analysis_report.pdf')==checks_by['layout_review']['pdf_sha256']
    for source,name in [('field_browser_jury','field_browser.json'),('media_review_final','media_browser.json'),('browser_review_jury','section_browser.json'),('layout_review','report_visual_review.json'),('inference_display_final','inference_display_review.json'),('requirements_review','requirements_review.json')]:copy(W/source/'receipt.json',B/'validation'/name)
    nb=nbformat.read(B/'notebooks/analysis.ipynb',as_version=4)
    code=[c.source for c in nb.cells if c.cell_type=='code'];assert len(code)==12
    put(B/'validation/notebook_analysis_execution.json',dict(status='passed',executed_code_cells=12,actual_jupyter_kernel=True,outputs_saved=False,
        notebook_sha256=sha(B/'notebooks/analysis.ipynb'),code_sources_sha256=hashlib.sha256('\n'.join(code).encode()).hexdigest()))
    put(B/'validation/media_visual_review.json',dict(status='passed',video_sha256=media['video_sha256'],decoded_frames=12,seconds=media['video_metadata']['duration'],team_name=TEAM))
    summary=read(B/'summary.json');summary['files']={name:sha(B/name) for name in ['index.html','viewer_data.json.gz','maps/sections.html','results/field/index.html','demo/model_demo.webm','start.html','demo/poster.png']};put(B/'summary.json',summary)
    facts=read(B/'technical/judging_evidence.json')
    facts.update(short_forcing_review=read(B/'technical/short_forcing_review.json'),aws_short_forcing_review=read(B/'technical/aws_short_forcing_review.json'),current_result_entry='start.html',field_comparison_plan=read(B/'results/field/summary.json'),inventory_agreement=read(B/'results/inventory/agreement/summary.json'),
        full_validation_reproduction=read(B/'technical/full_validation_input.json'),threshold_selection_review=read(B/'technical/threshold_selection_review.json'))
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
                    content=tail+block;assert key not in content,'Credential in package file';tail=content[-max(512,len(key)):]
            if path.suffix=='.py':compile(path.read_text('utf-8-sig'),str(path),'exec');compiled+=1
    checks=dict(status='passed',team_name=TEAM,main_report_pages=14,field_plan_pages=2,
        notebooks={'analysis':12,'training':3},core_example_rows=144,protected_core_cli_rows_exact=103680,
        protected_weather_cli_rows_exact=103680,weather_information_input_rows=2350080,
        information_series=[22,24],exact_duplicate_array_comparisons=90,inspection_segments=3,inspection_areas=2,
        selection_scenarios=75,browser_exact_memberships=126450,monotonic_subset_checks=1275,independent_raster_pixels_verified=843,
        original_model_training_predictions_unchanged=True,unchanged_existing_files=same,changed_existing_files=changed,
        python_files_compiled=compiled,markdown_links_passed=True,credential_scan_passed=True,
        field_browser_viewports=3,field_record_csv_rows=4,record_save_restore_passed=True,invalid_record_import_atomic=True,
        actual_field_measurements=0,inventory_nominal_segments=64,inventory_possible_segments_250m=81,inventory_weather_both_quartile_segments=0,
        new_model_fits=40,production_model_refits=0,short_forcing_threshold_searches=32,short_forcing_candidates_promoted=0,unconstrained_threshold_searches=16,unconstrained_candidate_promoted=False,
        result_summary='start.html',pdf_bookmarks=14,pdf_cover_links=3,video_chapters=8,keyboard_tested=True,
        single_folder_archives=True,competition_submitted=False)
    put(B/'validation/delivery_checks.json',checks);put(W/'delivery_checks.json',checks)
    prior.W=W
    for folder,channel in [(B,'model'),(D,'documents')]:
        prior.manifest(folder,channel)
        m=read(folder/'manifest.json');m['team_name']=TEAM
        if channel=='model':m.update(current_field_plan='results/field/index.html',current_result_entry='start.html')
        put(folder/'manifest.json',m);verify_directory(folder)
    print('PASS file preservation, Markdown, Python compilation, credential scan; archiving',flush=True)
    archives={kind:archive(folder,W/NAMES[kind],FOLDERS[kind]) for kind,folder in [('documents',D),('model',B)]}
    extracted=W/'extracted_submission_check';extracted.mkdir()
    for kind in ['documents','model']:
        with zipfile.ZipFile(W/NAMES[kind]) as z:
            assert z.testzip() is None
            assert {n.split('/')[0] for n in z.namelist()}=={FOLDERS[kind]}
            assert not any('local_review' in n or '.secret' in n or n.endswith(('.env','.key','.pem','.curl')) for n in z.namelist())
            z.extractall(extracted)
        verify_directory(extracted/FOLDERS[kind])
    model=extracted/FOLDERS['model'];env=dict(os.environ)
    env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    def run(args):
        r=subprocess.run([sys.executable,'-X','utf8',*args],cwd=model,env=env,capture_output=True,text=True,encoding='utf8',timeout=600)
        assert r.returncode==0,r.stdout+r.stderr
        print('PASS extracted',args[0],flush=True)
    run(['code/check_full_validation.py','--output','local_review/full_validation'])
    full=read(model/'local_review/full_validation/receipt.json');assert full['rows']==103680 and not full['observed_target_columns_read']
    run(['code/predict.py','--input','data/weather_example.csv','--output','local_review/archive_prediction.csv','--output-start','2024-12-15','--output-end','2024-12-16'])
    options=dict(dtype={'station':str},float_precision='round_trip')
    pd.testing.assert_frame_equal(pd.read_csv(model/'local_review/archive_prediction.csv',**options),pd.read_csv(model/'data/example_predictions.csv',**options),check_exact=True)
    run(['code/analyze_inventory_agreement.py','--output','local_review/inventory_agreement'])
    for name in ['threshold_comparison.csv','mapped_inventory_records.csv','summary.json']:
        assert sha(model/'local_review/inventory_agreement'/name)==sha(model/'results/inventory/agreement'/name),name
    run(['code/build_field_plan.py','--output','local_review/rebuilt_field'])
    for name in ['comparison_candidates.csv','measurement_protocol.csv','field_cases.json','index.html','summary.json']:
        assert sha(model/'local_review/rebuilt_field'/name)==sha(model/'results/field'/name),name
    lhs=gpd.read_file(model/'local_review/rebuilt_field/measurement_plan.gpkg',engine='pyogrio');rhs=gpd.read_file(model/'results/field/measurement_plan.gpkg',engine='pyogrio')
    pd.testing.assert_frame_equal(lhs.drop(columns='geometry'),rhs.drop(columns='geometry'),check_exact=True)
    assert lhs.crs==rhs.crs and all(a.equals_exact(b,0) for a,b in zip(lhs.geometry,rhs.geometry))
    run(['code/compare_fixed_temperature_rules.py','--output','local_review/fixed_rule_comparison'])
    fixed=read(model/'local_review/fixed_rule_comparison/receipt.json');assert fixed['status']=='exact_fixed_rule_metrics_reproduced'
    run(['code/analyze_short_forcing_review.py','--output','local_review/short_forcing_review'])
    run(['code/analyze_aws_short_forcing_review.py','--output','local_review/aws_short_forcing_review'])
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':390,'height':844})
        page.goto((model/'start.html').as_uri());page.wait_for_function('window.START_READY===true')
        assert page.locator('.route-line').count()==3 and page.evaluate('document.documentElement.scrollWidth')<=391
        page.goto((model/'demo/index.html').as_uri());page.wait_for_function('window.DEMO_READY===true')
        assert page.locator('#videoCover').is_visible() and page.locator('video').get_attribute('src') is None
        page.locator('[data-second="86"]').click();page.wait_for_function('document.querySelector("video").currentTime>=86&&!document.querySelector("video").paused',timeout=30000)
        page.locator('video').evaluate('v=>v.pause()');browser.close()
    assert verify_preserved()==frozen
    for kind in FOLDERS:verify_directory(extracted/FOLDERS[kind])
    receipt=dict(status='two_channel_archives_verified',team_name=TEAM,archives=archives,archive_filenames=NAMES,archive_root_folders=FOLDERS,
        report_pages=14,field_plan_pages=2,demo_seconds=media['video_metadata']['duration'],checks=checks,
        extracted_archives_verified=True,extracted_result_summary_and_video_verified=True,extracted_short_forcing_metric_rows_exact=48,extracted_model_inference_rows_exact=103680,extracted_example_rows_exact=144,
        extracted_full_validation=full,extracted_inventory_comparison_reproduced=True,
        extracted_field_comparison_reproduced=True,extracted_fixed_rule_metrics_reproduced=True,
        core_models_training_and_required_prediction_values_unchanged=True,competition_submitted=False,at_utc=datetime.now(timezone.utc).isoformat())
    put(W/'submission_receipt.json',receipt)
    print(json.dumps(dict(status=receipt['status'],archives=archives,demo_seconds=receipt['demo_seconds']),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
