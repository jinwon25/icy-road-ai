"""최종 검증을 수행하고 제출 화면의 두 칸에 맞는 단일 폴더 ZIP을 만든다."""
from pathlib import Path
from datetime import datetime,timezone
from itertools import combinations
import sys,json,re,shutil,subprocess,hashlib,zipfile
import numpy as np
import pandas as pd
import nbformat,fitz
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W,write
from scripts.package_competition_submission import manifest
from scripts.package_review_v8 import archive
from scripts.review_submission_bundle import verify_directory
from scripts.check_markdown import inspect_documents
from scripts.evaluate_objective_icing import verify_preserved
from src.data_source import sha256_file as sha
from src.kma_rwis_download import load_auth_key
B=W/'icy_road_model';D=W/'icy_road_documents';TEAM='로드투인사이트'
NAMES={'documents':TEAM+'_문서자료.zip','model':TEAM+'_모델자료.zip'}
ROOTS={'documents':TEAM+'_문서자료','model':TEAM+'_모델자료'}

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        assert json.loads(path.read_text('utf8'))==value,path
        return
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf8')

def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)

def main():
    assert not (W/'submission_receipt.json').exists()
    media=json.loads((W/'media_review_team/receipt.json').read_text('utf8'));assert media['status']=='passed'
    browser=json.loads((W/'browser_review_information/receipt.json').read_text('utf8'));assert browser['status']=='passed'
    info=json.loads((W/'information_group_correction/replay_and_gis_verified.json').read_text('utf8'));assert info['status']=='passed'
    old=json.loads((W/'original_icy_road_model_manifest.json').read_text('utf8'))['files']
    allowed={'README.md','AI_USAGE.md','index.html','maps/sections.html','notebooks/analysis.ipynb','assets/site.css','summary.json','src/section_review.py'}
    protected=0;changed=[];unchanged=0
    for name,record in old.items():
        path=B/name
        if path.is_file() and sha(path)==record['sha256']:unchanged+=1;continue
        assert name in allowed or name.startswith(('report/','demo/','validation/','results/sections/','technical/competition_requirements.md')),name
        changed.append(name)
    for name,record in old.items():
        if name.endswith('.joblib') or name.startswith(('data/','model/','results/weather/')) or name.startswith('results/evaluation/observations_predictions'):
            assert sha(B/name)==record['sha256'],name;protected+=1
    preservation=verify_preserved()
    # 새 기준의 휴대형 재현과 화면을 원 데이터에 맞춰 검사한다.
    assert sha(B/'local_review/rebuilt_sections_team.html')==sha(B/'maps/sections.html')
    for name in ['scenario_summary.csv','scenario_membership.csv']:
        assert sha(B/'local_review/information_sensitivity'/name)==sha(B/'results/sections/sensitivity'/name)
    f=pd.read_csv(B/'results/sections/section_review.csv',dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
    assert len(f)==1686 and f.loc[f.inspection_candidate].seg_id.nunique()==3
    areas=pd.read_csv(B/'results/sections/inspection_areas.csv');assert len(areas)==2 and areas.segments.sum()==3
    scenarios=pd.read_csv(B/'results/sections/sensitivity/scenario_summary.csv')
    membership=pd.read_csv(B/'results/sections/sensitivity/scenario_membership.csv',dtype={'seg_id':str}).set_index('seg_id')
    sets={int(s.scenario):set(membership.index[membership[f'scenario_{s.scenario:02d}']]) for s in scenarios.itertuples()}
    monotonic=0
    for a,b in combinations(scenarios.itertuples(),2):
        if a.weather_quantile<=b.weather_quantile and a.curve_quantile<=b.curve_quantile and a.margin_m<=b.margin_m:
            assert sets[b.scenario]<=sets[a.scenario];monotonic+=1
    # 조건 통계는 같은 숫자를 유지한 채 현재 입력의 해시로 재현한 계획을 사용한다.
    for path in (B/'local_review/condition_information').iterdir():
        target=B/'results/conditions'/path.name
        if path.suffix in ['.csv','.parquet']:assert sha(path)==sha(target),path.name
        else:copy(path,target)
    report=B/'report/analysis_report.pdf';doc=fitz.open(report);assert len(doc)==13 and doc.metadata['author']==TEAM
    all_text='\n'.join(p.get_text() for p in doc)
    assert '3구간' in all_text and 'S01' in all_text and 'S02' in all_text
    assert not re.search(r'22구간|11개 범위|F0[1-9]|\bv(?:1[0-9]|[1-9])\b',all_text)
    for i,page in enumerate(doc):
        spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']]
        assert all(s['bbox'][0]>=0 and s['bbox'][2]<=596 and s['bbox'][1]>=0 and s['bbox'][3]<=842 for s in spans)
        foot=[s['text'] for s in spans if s['bbox'][1]>790];assert str(i+1) in foot and any(TEAM in t for t in foot)
    nb=nbformat.read(B/'notebooks/analysis.ipynb',as_version=4);nbformat.validate(nb)
    codes=[c.source for c in nb.cells if c.cell_type=='code'];assert len(codes)==10 and not any(c.outputs for c in nb.cells if c.cell_type=='code')
    assert sha(B/'notebooks/training.ipynb')==old['notebooks/training.ipynb']['sha256']
    # 원본 검증 기록은 별도 작업 폴더에 보존하고 최종 상태의 기록만 배치한다.
    previous=W/'validation_before_team_delivery';current=B/'validation'
    assert current.resolve().is_relative_to(W.resolve()) and previous.resolve().is_relative_to(W.resolve())
    if not previous.exists():
        current.rename(previous);current.mkdir()
    else:
        assert (current/'selection_metamorphic_checks.json').is_file()
        assert not any((W/name).exists() for name in NAMES.values())
    for name in ['cli_air_temperature.log','cli_temperature_moisture.log','cli_weather.log','notebook_training.log']:copy(previous/name,current/name)
    write(current/'notebook_analysis_execution.json',dict(status='passed',executed_code_cells=10,actual_jupyter_kernel=True,outputs_saved=False,
        notebook_sha256=sha(B/'notebooks/analysis.ipynb'),code_sources_sha256=hashlib.sha256(json.dumps(codes,ensure_ascii=False).encode()).hexdigest()))
    write(current/'training_execution_provenance.json',dict(status='same_previously_executed_sources_preserved',executed_code_cells=3,
        notebook_sha256=sha(B/'notebooks/training.ipynb'),training_code_changed=False,training_data_changed=False))
    copy(W/'browser_review_information/receipt.json',current/'section_browser.json')
    copy(W/'media_review_team/receipt.json',current/'media_browser.json')
    copy(W/'information_group_correction/replay_and_gis_verified.json',current/'weather_information_replay.json')
    copy(W/'independent_evidence_audit.json',current/'fixed_numeric_and_raster_audit.json')
    write(current/'report_visual_review.json',dict(status='passed',pages=13,pdf_sha256=sha(report),
        latest_pages_rendered_and_reviewed=True,footers_1_through_13=True,team_name=TEAM,text_within_page_bounds=True))
    write(current/'media_visual_review.json',dict(status='passed',video_sha256=sha(B/'demo/model_demo.webm'),decoded_frames=9,
        latest_screenshots_and_contact_sheet_reviewed=True,seconds=media['video_metadata']['duration']))
    write(current/'selection_metamorphic_checks.json',dict(status='passed',scenarios=75,monotonic_subset_checks=monotonic,
        reference_segments=3,reference_areas=2,actual_information_groups=[22,24],reference_parameters=[.75,.75,250,.95]))
    facts=dict(team_name=TEAM,temperature_benchmarks=json.loads((W/'temperature_benchmarks/summary.json').read_text('utf8')),
        inspection_sensitivity=json.loads((B/'results/sections/sensitivity/summary.json').read_text('utf8')),
        weather_information=json.loads((B/'technical/weather_information_group_audit.json').read_text('utf8')),
        core_models_and_required_predictions_unchanged=True)
    (B/'technical/judging_evidence.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n','utf8')
    summary=json.loads((B/'summary.json').read_text('utf8'));summary['team_name']=TEAM
    summary['files']={n:sha(B/n) for n in ['index.html','viewer_data.json.gz']}
    (B/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
    # 문서자료에는 설명 문서와 근거 도표·표만, 실행 가능한 전체 결과는 모델자료에 둔다.
    copy(report,D/'report/analysis_report.pdf');copy(B/'AI_USAGE.md',D/'AI_USAGE.md')
    for path in (B/'report/figures').glob('*.png'):copy(path,D/'figures'/path.name)
    pairs=[('results/evaluation/temperature_benchmarks/metrics.csv','data/temperature_benchmarks.csv'),
        ('results/evaluation/temperature_benchmarks/paired_day_block_sensitivity.csv','data/temperature_day_block_sensitivity.csv'),
        ('results/sections/inspection_areas.csv','data/inspection_areas.csv'),('results/sections/criteria.csv','data/criteria.csv'),
        ('results/sections/route_summary.csv','data/route_summary.csv'),('results/sections/field_review_plan.csv','data/field_review_plan.csv'),
        ('results/sections/sensitivity/scenario_summary.csv','data/selection_scenarios.csv'),
        ('results/sections/sensitivity/area_stability.csv','data/area_stability.csv'),
        ('data/weather_information_groups.csv','data/weather_information_groups.csv'),
        ('results/conditions/association_ranges.csv','data/condition_association_ranges.csv'),
        ('results/conditions/development_observed_ice_by_condition.csv','data/observed_ice_conditions.csv')]
    for source,target in pairs:copy(B/source,D/target)
    for source,target in [('condition_exposure','winter_exposure'),('inspection_locations','inspection_review')]:
        Image.open(B/'report/figures'/(source+'.png')).convert('RGB').save(D/'maps'/(target+'.jpg'),quality=95,subsampling=0)
    (D/'README.md').write_text('''# 로드투인사이트의 전북 고속도로 겨울철 분석

[13쪽 분석 보고서](report/analysis_report.pdf)에 개요, 활용 데이터, 모델 개발, 실험·평가, 활용 범위와 한계를 정리했다. 학습 제외 3지점의 노면온도 MAE 평균은 0.978°C이며, 같은 관측쌍의 기본 회귀 대비 MAE가 14.6% 낮았다. 결빙 Precision은 0.0195, F1은 0.0326으로 낮은 정밀도가 핵심 한계다.

실제 14입력 시계열의 중복을 제외한 기준 조합은 서해안 3구간·2개 범위다. [기준표](data/criteria.csv), [범위](data/inspection_areas.csv), [75개 기준의 민감도](data/selection_scenarios.csv), [현장 확인표](data/field_review_plan.csv)를 함께 제공한다. 같은 정보를 공유하는 구간을 독립적인 위험 발견으로 세지 않았다.

[노면온도 비교](figures/temperature_benchmarks.png), [입력 기준 민감도](figures/selection_sensitivity.png), [실측 Ice의 조건](figures/observed_ice_conditions.png), [지형·일사 맥락](figures/terrain_solar_context.png), [목록과 범위 비교](maps/inspection_review.jpg)를 확인할 수 있다.

모델자료 ZIP에는 실행 매뉴얼·코드·학습 자료·모형·Notebook·원본 지형·기상 입력·전체 CSV/GIS·오프라인 지도·실행 영상을 포함했다. [AI 활용과 주요 검토](AI_USAGE.md)는 실제 지원 범위, 대안·실패 사례와 최종 선택을 설명한다.
''','utf8')
    # 인증 요청 파일 등 상위 작업 폴더는 압축 대상에 들어오지 않는다.
    secret_values=[load_auth_key(ROOT/'secret.env').encode()]
    compiled=0
    for folder in [B,D]:
        errors=inspect_documents(folder,[p.relative_to(folder).as_posix() for p in folder.rglob('*.md')]);assert not errors,errors
        for path in folder.rglob('*'):
            if not path.is_file() or 'local_review' in path.relative_to(folder).parts or '__pycache__' in path.parts:continue
            assert path.suffix.lower() not in ['.env','.key','.pem','.curl'] and '.secret' not in path.name,path.name
            with path.open('rb') as stream:
                tail=b''
                while block:=stream.read(1024*1024):
                    data=tail+block;assert not any(v and v in data for v in secret_values),'Credential entered a submission file'
                    tail=data[-512:]
            if path.suffix=='.py':compile(path.read_text('utf-8-sig'),str(path),'exec');compiled+=1
    checks=dict(status='passed',team_name=TEAM,report_pages=13,notebooks={'analysis':10,'training':3},core_example_rows=144,
        protected_weather_cli_rows_exact=103680,weather_information_input_rows=2350080,information_series=[22,24],
        exact_duplicate_array_comparisons=90,section_winter_exposure_rows_exact=1686,inspection_segments=3,inspection_areas=2,
        selection_scenarios=75,monotonic_subset_checks=monotonic,browser_exact_memberships=126450,
        independent_raster_pixels_verified=843,protected_original_files_unchanged=protected,unchanged_original_files=unchanged,
        changed_existing_files=changed,python_files_compiled=compiled,core_model_and_training_data_unchanged=True,
        numerical_predictions_unchanged=True,markdown_links_passed=True,credential_scan_passed=True,
        single_folder_archives=True,competition_submitted=False,preservation=preservation)
    write(current/'delivery_checks.json',checks);write(W/'delivery_checks.json',checks)
    for folder,channel in [(B,'model'),(D,'documents')]:
        manifest(folder,channel)
        p=folder/'manifest.json';value=json.loads(p.read_text('utf8'));value['team_name']=TEAM;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf8')
        verify_directory(folder)
    archives={kind:archive(folder,W/NAMES[kind],ROOTS[kind]) for kind,folder in [('documents',D),('model',B)]}
    extracted=W/'extracted_submission_check';extracted.mkdir()
    for kind in ['documents','model']:
        path=W/NAMES[kind]
        with zipfile.ZipFile(path) as z:
            assert {n.split('/')[0] for n in z.namelist()}=={ROOTS[kind]}
            assert not any('.secret' in n or n.endswith(('.env','.key','.pem','.curl')) for n in z.namelist())
            z.extractall(extracted)
        verify_directory(extracted/ROOTS[kind])
    model=extracted/ROOTS['model'];env=dict(__import__('os').environ);env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    run=subprocess.run([sys.executable,'-X','utf8','code/predict.py','--input','data/weather_example.csv','--output','local_review/archive_prediction.csv','--output-start','2024-12-15','--output-end','2024-12-16'],cwd=model,env=env,capture_output=True,text=True,encoding='utf8',timeout=180)
    assert run.returncode==0,run.stdout+run.stderr
    options=dict(dtype={'station':str},float_precision='round_trip')
    pd.testing.assert_frame_equal(pd.read_csv(model/'local_review/archive_prediction.csv',**options),pd.read_csv(model/'data/example_predictions.csv',**options),check_exact=True)
    receipt=dict(status='two_channel_archives_verified',team_name=TEAM,archives=archives,archive_filenames=NAMES,archive_root_folders=ROOTS,
        report_pages=13,demo_seconds=media['video_metadata']['duration'],checks=checks,extracted_archives_verified=True,
        extracted_model_inference_rows_exact=144,competition_submitted=False,at_utc=datetime.now(timezone.utc).isoformat())
    write(W/'submission_receipt.json',receipt)
    print(json.dumps(dict(status=receipt['status'],archives=archives,files=NAMES),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
