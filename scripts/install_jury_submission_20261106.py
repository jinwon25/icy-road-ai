"""검증된 두 제출 파일을 설치하고 이전 제출본과 원문 안내를 보존한다."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.review_submission_bundle import verify_directory
from scripts.check_markdown import inspect_documents
P=ROOT/'outputs/private';W=P/'final_jury_review_20261106';CURRENT=P/'competition_submission'
BACKUP=P/'competition_submission_before_jury_review_20261106';STAGE=W/'release'
def read(p):return json.loads(p.read_text('utf8'))

def main():
    final=read(W/'submission_receipt.json');baseline=read(W/'baseline_receipt.json')
    assert final['status']=='two_channel_archives_verified'
    assert final['extracted_model_inference_rows_exact']==103680 and final['extracted_inventory_comparison_reproduced']
    assert final['extracted_field_comparison_reproduced'] and final['extracted_fixed_rule_metrics_reproduced']
    assert not STAGE.exists() and not BACKUP.exists()
    for p in [CURRENT,BACKUP,STAGE]:assert p.resolve().is_relative_to(P.resolve())
    for kind,name in final['archive_filenames'].items():
        assert sha(CURRENT/name)==baseline['archives'][kind]['sha256']
        assert sha(W/name)==final['archives'][kind]['sha256']
    root_docs={'COMPETITION_REQUIREMENTS.md':'docs/competition/COMPETITION_REQUIREMENTS.md','STATUS.md':'docs/STATUS.md'}
    for name,target in root_docs.items():
        assert (W/'current_project_documents'/name).is_file()
        # A separately edited root document must be preserved instead of overwritten.
        assert sha(ROOT/target)==sha(W/'documents_before_review'/target),target
        backup=W/'documents_before_install'/name;backup.parent.mkdir(exist_ok=True)
        assert not backup.exists();shutil.copyfile(ROOT/target,backup)
    STAGE.mkdir()
    for folder in ['icy_road_model','icy_road_documents']:
        shutil.copytree(W/folder,STAGE/folder,ignore=shutil.ignore_patterns('local_review','__pycache__','*.pyc'));verify_directory(STAGE/folder)
    for name in final['archive_filenames'].values():shutil.copy2(W/name,STAGE/name)
    shutil.copy2(W/'submission_receipt.json',STAGE/'submission_receipt.json')
    note=(W/'JURY_REVIEW.md').read_text('utf8').replace('표기를 수정할 준비를 했다.','표기를 수정했다.')
    (STAGE/'JURY_REVIEW.md').write_text(note,'utf8')
    (STAGE/'README.md').write_text('''# 로드투인사이트 제출 자료

결과제출 화면의 문서자료와 모델자료에 아래 ZIP을 각각 선택한다. 각 ZIP에는 한 개의 최상위 폴더가 들어 있다.

| 제출 항목 | 파일 | 내용 |
| --- | --- | --- |
| 문서자료 | [로드투인사이트_문서자료.zip](로드투인사이트_문서자료.zip) | 14쪽 분석 보고서, 2쪽 현장 확인 계획, 도표·원표, AI 활용 내역 |
| 모델자료 | [로드투인사이트_모델자료.zip](로드투인사이트_모델자료.zip) | 실행 매뉴얼·코드·모형·학습·검증 입력·Notebook·전체 CSV/GIS·오프라인 지도·약 92초 실제 실행 영상 |

[분석 보고서](icy_road_model/report/analysis_report.pdf) · [기상 지도](icy_road_model/index.html) · [구간 검토](icy_road_model/maps/sections.html) · [현장 확인 계획](icy_road_model/results/field/index.html) · [실행 영상](icy_road_model/demo/index.html) · [실행 안내](icy_road_model/README.md)

압축 해제본에서 전체 기간의 온도·결빙 예측 103,680행과 예제 144행을 정확히 재현했다. 공개 목록 대조, 현장 확인 계획, 고정 규칙 비교도 포함된 코드로 재계산했다. 파일별 SHA-256과 압축 무결성, 실행 확인은 submission_receipt.json과 각 폴더의 manifest.json에 기록했다. 현장 기록은 미측정 상태다.

현재 결과의 강점과 남은 약점은 [심사 관점 검토](JURY_REVIEW.md)에 정리했다. 이 메모는 두 제출 ZIP 바깥에 둔 팀 확인 자료다.

마감은 **2026년 11월 6일 23:59 KST**다. 파일 업로드 후 제출 이력의 완료 상태를 확인해야 한다. 실제 업로드와 제출 버튼 클릭은 수행하지 않았다.

[공식 심사 기준](https://aida.kisti.re.kr/competition/main/overview.do) · [업로드 안내](https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=807) · [최종 제출물 안내](https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=811)

최신 공지·공통 Q&A 목록과 공통 심사 기준을 다시 확인했다. 일부 상세 답변 본문은 재접속되지 않아 오늘 15:35 KST에 확보한 본문과 구분했다. 확인 범위는 모델자료 technical/official_evening_access_review.json에 기록했다.
''','utf8')
    assert not inspect_documents(STAGE,['README.md','JURY_REVIEW.md'])
    CURRENT.rename(BACKUP)
    try:STAGE.rename(CURRENT)
    except BaseException:BACKUP.rename(CURRENT);raise
    for name,target in root_docs.items():shutil.copyfile(W/'current_project_documents'/name,ROOT/target)
    errors=inspect_documents(ROOT,['README.md','docs/STATUS.md','docs/START_HERE.md','docs/competition/COMPETITION_REQUIREMENTS.md']);assert not errors,errors
    for kind,name in final['archive_filenames'].items():
        assert sha(CURRENT/name)==final['archives'][kind]['sha256']
        assert sha(BACKUP/name)==baseline['archives'][kind]['sha256']
    for folder in ['icy_road_model','icy_road_documents']:verify_directory(CURRENT/folder)
    result=dict(status='installed_verified',path=str(CURRENT),backup=str(BACKUP),files={k:str(CURRENT/n) for k,n in final['archive_filenames'].items()},
        bytes={k:v['bytes'] for k,v in final['archives'].items()},sha256={k:v['sha256'] for k,v in final['archives'].items()},
        main_report_pages=14,field_plan_pages=2,demo_seconds=final['demo_seconds'],full_core_predictions_exact=103680,
        current_root_document_links_verified=True,competition_submitted=False,at_utc=datetime.now(timezone.utc).isoformat())
    (W/'installed_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
