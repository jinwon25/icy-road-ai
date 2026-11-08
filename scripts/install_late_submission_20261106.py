"""최종 검증된 두 ZIP과 열람 화면을 교체하고 이전 제출본을 그대로 보관한다."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.review_submission_bundle import verify_directory
from scripts.check_markdown import inspect_documents
P=ROOT/'outputs/private';W=P/'late_research_design_20261106';CURRENT=P/'competition_submission';BACKUP=P/'competition_submission_before_navigation_20261106';STAGE=W/'release'
def read(p):return json.loads(p.read_text('utf8'))
def main():
    final=read(W/'submission_receipt.json');baseline=read(W/'baseline_receipt.json')
    assert final['status']=='two_channel_archives_verified' and final['extracted_result_summary_and_video_verified'] and final['extracted_model_inference_rows_exact']==103680
    assert not STAGE.exists() and not BACKUP.exists()
    for p in [CURRENT,BACKUP,STAGE]:assert p.resolve().is_relative_to(P.resolve())
    for kind,name in final['archive_filenames'].items():
        assert sha(CURRENT/name)==baseline['archives'][kind]['sha256'];assert sha(W/name)==final['archives'][kind]['sha256']
    docs={'README.md':'README.md','START_HERE.md':'docs/START_HERE.md','STATUS.md':'docs/STATUS.md'}
    for name,target in docs.items():assert sha(ROOT/target)==sha(W/'root_documents_before'/target),target
    STAGE.mkdir()
    for folder in ['icy_road_model','icy_road_documents']:
        shutil.copytree(W/folder,STAGE/folder,ignore=shutil.ignore_patterns('local_review','__pycache__','*.pyc'));verify_directory(STAGE/folder)
    for name in final['archive_filenames'].values():shutil.copy2(W/name,STAGE/name)
    shutil.copy2(W/'submission_receipt.json',STAGE/'submission_receipt.json');shutil.copy2(W/'JURY_REVIEW.md',STAGE/'JURY_REVIEW.md')
    (STAGE/'README.md').write_text('''# 로드투인사이트 제출 자료

[결과 요약](icy_road_model/start.html) · [분석 결과와 실행 영상](icy_road_model/demo/index.html) · [분석 보고서](icy_road_model/report/analysis_report.pdf) · [구간 검토](icy_road_model/maps/sections.html) · [현장 확인 계획](icy_road_model/results/field/index.html)

결과제출 화면의 문서자료와 모델자료에 아래 ZIP을 각각 선택한다. 각 ZIP에는 한 개의 최상위 폴더가 들어 있다.

| 제출 항목 | 파일 | 내용 |
| --- | --- | --- |
| 문서자료 | [로드투인사이트_문서자료.zip](로드투인사이트_문서자료.zip) | 14쪽 보고서, 2쪽 현장 확인 계획, 도표·원표, AI 활용 내역 |
| 모델자료 | [로드투인사이트_모델자료.zip](로드투인사이트_모델자료.zip) | 실행 안내·코드·모형·학습·검증 입력·Notebook·CSV/GIS·결과 요약·주제별 분석·오프라인 지도·92초 실행 영상 |

보고서는 첫 쪽의 질문별 이동과 14개 책갈피를 제공한다. 데모에서는 온도 추정·결빙 판정·구간 확인을 주제별로 읽고, 8개 장면을 골라 재생할 수 있다. 두 화면은 별도 서버나 인터넷 연결 없이 열린다.

압축 해제본에서 전체 온도·결빙 예측 103,680행과 예제 144행을 정확히 재현했다. 목록 대조, 현장 확인 계획, 고정 규칙 비교, 두 단기 이력 연구의 48개 지표 행도 재계산했다. 파일 무결성과 실행 확인은 submission_receipt.json에 기록했다.

[실행 안내](icy_road_model/README.md) · [심사 관점 검토](JURY_REVIEW.md) · [AI 활용 내역](icy_road_model/AI_USAGE.md)

마감은 **2026년 11월 6일 23:59 KST**다. 실제 사이트 업로드와 제출 버튼 클릭은 수행하지 않았다. 업로드 후 제출 이력의 완료 상태를 확인해야 한다.

공식 공통 심사 기준·공지·Q&A 목록을 마무리 단계에서 다시 확인했다. 과제의 일부 상세 답변은 재접속되지 않아 오늘 15:35 KST에 확보한 공식 본문과 구분해 대조했다. 확인 범위와 한계는 모델자료 technical/official_evening_access_review.json에 기록했다.
''','utf8')
    assert not inspect_documents(STAGE,['README.md','JURY_REVIEW.md'])
    CURRENT.rename(BACKUP)
    try:STAGE.rename(CURRENT)
    except BaseException:BACKUP.rename(CURRENT);raise
    for name,target in docs.items():shutil.copyfile(W/'current_project_documents'/name,ROOT/target)
    assert not inspect_documents(ROOT,['README.md','docs/START_HERE.md','docs/STATUS.md','docs/competition/COMPETITION_REQUIREMENTS.md'])
    for kind,name in final['archive_filenames'].items():
        assert sha(CURRENT/name)==final['archives'][kind]['sha256'] and sha(BACKUP/name)==baseline['archives'][kind]['sha256']
    for folder in ['icy_road_model','icy_road_documents']:verify_directory(CURRENT/folder)
    receipt=dict(status='installed_verified',path=str(CURRENT),backup=str(BACKUP),
        files={k:str(CURRENT/n) for k,n in final['archive_filenames'].items()},
        bytes={k:v['bytes'] for k,v in final['archives'].items()},sha256={k:v['sha256'] for k,v in final['archives'].items()},
        report_pages=14,pdf_bookmarks=14,pdf_cover_links=3,video_seconds=final['demo_seconds'],video_chapters=8,
        full_prediction_rows_exact=103680,competition_submitted=False,at_utc=datetime.now(timezone.utc).isoformat())
    (W/'installed_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
