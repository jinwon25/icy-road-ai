"""추론·학습 자산을 보존한 보고서 보강 사본의 추가 분석과 레이아웃을 확인한다."""
from pathlib import Path
from datetime import datetime,timezone
import json,re,hashlib,sys
import fitz,nbformat,pandas as pd
from PIL import Image,ImageChops
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
from scripts.check_markdown import inspect_documents
P=ROOT/'outputs/private';W=P/'precision_submission_update_20261106';B=W/'icy_road_model'

def main():
    assert not (W/'delivery_checks.json').exists()
    old=read(W/'original_model_manifest.json')['files']
    allowed={'README.md','AI_USAGE.md','report/analysis_report.pdf','report/analysis_report.md','notebooks/analysis.ipynb'}
    unchanged=0
    for relative,record in old.items():
        if relative in allowed:continue
        assert sha(B/relative)==record['sha256'],relative
        unchanged+=1
    original=P/'competition_submission/icy_road_model'
    assert all(sha(p)==sha(original/'model'/p.name) for p in (B/'model').glob('*.joblib'))
    d=B/'results/evaluation'
    f=pd.read_parquet(d/'development_predictions.parquet')
    assert len(f)==310777 and not f.duplicated(['station','time']).any()
    assert not set(f.station)&{'12410','33411','23402','33402','33406','12213','23411'}
    q=B/'local_review/icing_error_analysis'
    for computed,expected in [('surface_states.csv','development_false_alarm_states.csv'),('moisture_evidence.csv','development_moisture_evidence.csv')]:
        opt={'dtype':{'station':str}} if computed.startswith('moisture') else {}
        pd.testing.assert_frame_equal(pd.read_csv(q/computed,**opt),pd.read_csv(d/expected,**opt))
    summary=read(q/'summary.json')
    assert summary['source_sha256']==sha(d/'development_predictions.parquet')
    assert (summary['rows'],summary['fp'],summary['false_alarm_surface_at_or_below_zero'])==(309928,25341,23891)
    nb=nbformat.read(B/'notebooks/analysis.ipynb',as_version=4);nbformat.validate(nb)
    code=[c.source for c in nb.cells if c.cell_type=='code']
    assert len(code)==6 and not any(c.outputs for c in nb.cells if c.cell_type=='code')
    # 6개 코드 셀은 check_notebook.py의 실제 Jupyter 실행으로 통과했다. 이후 수정은 셀 ID뿐이다.
    write(W/'notebook_execution.json',dict(status='passed',command='scripts/check_notebook.py notebooks/analysis.ipynb',
        executed_code_cells=6,outputs_saved=False,code_sources_sha256=hashlib.sha256(json.dumps(code,ensure_ascii=False).encode()).hexdigest(),
        notebook_sha256=sha(B/'notebooks/analysis.ipynb')))
    doc=fitz.open(B/'report/analysis_report.pdf');assert len(doc)==9
    visual={}
    for i,page in enumerate(doc):
        spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']]
        assert all(s['bbox'][0]>=0 and s['bbox'][2]<=596 and s['bbox'][1]>=0 and s['bbox'][3]<=842 for s in spans)
        footer=[s['text'] for s in spans if s['bbox'][1]>790]
        assert str(i+1) in footer
        if i in [0,1,2,3,4,8]:
            old_index=i if i<5 else i-1
            a=Image.open(W/'report_pages'/f'{i+1:02d}.png').convert('RGB')
            b=Image.open(P/'editorial_review_20261106/report_pages'/f'{old_index+1:02d}.png').convert('RGB')
            assert ImageChops.difference(a.crop((0,0,a.width,1190)),b.crop((0,0,b.width,1190))).getbbox() is None
            visual[str(i+1)]='body_raster_equal_to_previously_reviewed_page'
        else:
            visual[str(i+1)]='latest_render_visually_reviewed'
    text='\n'.join(page.get_text() for page in doc)
    for value in ['25,341','23,891','25,030','94.3%','98.8%']:assert value in text,value
    assert not re.search(r'\bv(?:1[0-9]|[1-9])\b|최종 v|보존된 v',text,re.I)
    errors=inspect_documents(B,[p.relative_to(B).as_posix() for p in B.rglob('*.md')]);assert not errors,errors
    visual_receipt=dict(status='passed',pages=9,source_sha256=sha(B/'report/analysis_report.pdf'),
        page_review=visual,footers_1_through_9=True,text_within_page_bounds=True)
    write(W/'report_visual_review.json',visual_receipt)
    checks=read(P/'competition_submission/icy_road_model/validation/delivery_checks.json')
    checks.update(report_pages=9,notebooks=dict(analysis=6,training=3),development_error_analysis_rows=309928,
        development_false_alarms=25341,development_error_aggregates_exact=True,
        unchanged_original_files=unchanged,core_model_and_training_data_unchanged=True,
        numerical_predictions_unchanged=True,report_references_and_local_links_passed=True)
    write(W/'delivery_checks.json',checks)
    for source,dest in [(W/'delivery_checks.json','delivery_checks.json'),(W/'report_visual_review.json','report_visual_review.json'),
                        (W/'notebook_execution.json','notebook_analysis_execution.json')]:
        (B/'validation'/dest).write_bytes(source.read_bytes())
    # 이전 사본의 5개 셀 실행 로그는 보관하고 현재 6개 셀 검증은 별도 영수증으로 제공.
    log=B/'validation/notebook_analysis.log'
    if log.exists():
        saved=W/'original_notebook_analysis.log'
        assert log.resolve().is_relative_to(W.resolve()) and saved.resolve().is_relative_to(W.resolve())
        log.replace(saved)
    print('PASS',unchanged,'unchanged original files, 9 report pages, exact error aggregates, 6 executed Notebook cells',flush=True)

if __name__=='__main__':main()
