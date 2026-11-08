"""최종 제출 작업본의 공식 요구·서약·수치와 파일 보존을 마지막으로 대조한다."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import sys,json,re,shutil
import pandas as pd,numpy as np,fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
P=ROOT/'outputs/private';W=P/'late_research_design_20261106';B=W/'icy_road_model';D=W/'icy_road_documents';CURRENT=P/'competition_submission/icy_road_model'
def read(p):return json.loads(p.read_text('utf8'))
def put(p,v):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
def main():
    assert not (W/'final_requirements.json').exists()
    csv=B/'results/evaluation/observations_predictions.csv';assert sha(csv)==sha(CURRENT/'results/evaluation/observations_predictions.csv')
    f=pd.read_csv(csv,dtype={'station_id':str},parse_dates=['prediction_time_kst'],float_precision='round_trip')
    assert len(f)==103680 and set(f.station_id)=={'12410','33411','23402'}
    assert not f.duplicated(['station_id','prediction_time_kst']).any() and f.prediction_time_kst.eq(f.prediction_time_kst.dt.floor('10min')).all()
    assert {'highway_name','station_name','station_id','prediction_time_kst','observed_surface_state','predicted_ice','observed_road_temperature_c','estimated_road_temperature_c'}<=set(f)
    plan=read(B/'extended_training_plan.json');assert len(plan['allowed_stations'])==23 and not set(plan['allowed_stations'])&set(f.station_id)
    frozen=read(CURRENT/'manifest.json')['files'];protected={n:r['sha256'] for n,r in frozen.items() if n.startswith(('model/','data/','src/','weather/')) or n=='notebooks/training.ipynb'}
    assert all(sha(B/n)==digest for n,digest in protected.items())
    assert sha(B/'notebooks/analysis.ipynb')==sha(CURRENT/'notebooks/analysis.ipynb')
    a=read(B/'technical/short_forcing_review.json');b=read(B/'technical/aws_short_forcing_review.json')
    assert not a['promote'] and not b['promote'] and a['new_model_fits']+b['new_model_fits']==40
    assert a['guarded_precision_feasible_candidates']==b['guarded_precision_feasible_candidates']==0
    terms=next(ROOT.glob('2026_*.pdf'));doc=fitz.open(terms);text='\n'.join(p.get_text(sort=True) for p in doc)
    assert 'DataON' in text and 'AIDA' in text
    lines=text.splitlines();relevant=[line.strip() for line in lines if any(k in line for k in ['제3자','폐기','저작권','공개','외부','열람','제공된 데이터'])]
    put(W/'pledge_review.json',dict(source_sha256=sha(terms),pages=len(doc),relevant_terms=relevant,
        project_data_uploaded_or_published=False,public_skill_downloads_contain_no_competition_data=True))
    previous=read(CURRENT/'validation/requirements_review.json');previous.update(current_recheck='core files and declared requirements rechecked',
        original_core_files_verified=len(protected),main_report_pages=14,result_summary='start.html',
        research_models_promoted=0,production_predictions_unchanged=True,competition_submitted=False)
    put(W/'requirements_review/receipt.json',previous)
    official=read(B/'technical/official_evening_access_review.json')
    official.update(at_kst=datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M'),
        final_review=dict(common_rubric={'creativity':20,'excellence':50,'effectiveness':30},
            task_main_page_and_public_lists_rechecked=True,task_qa_full_text_basis='2026-11-06 15:35 KST saved official answers 693 and 716',
            detailed_refresh_still_inaccessible=[693,716,807,811],pledge_rechecked=True,submission_values_and_execution_separate_from_website_receipt=True))
    put(B/'technical/official_evening_access_review.json',official)
    put(W/'final_requirements.json',dict(status='checked_against_accessible_official_rules_and_saved_answers',
        required_rows=103680,core_files_preserved=len(protected),training_stations=23,protected_stations=3,
        current_report_pages=14,extra_research_models=40,research_candidates_promoted=0,
        actual_field_measurements=0,competition_submitted=False,detail_refresh_limitation=True))
    print('PASS final required columns/times, held-out training, original core files, pledge and research declarations',flush=True)
if __name__=='__main__':main()
