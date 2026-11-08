"""검증된 최종 두 ZIP과 열람용 폴더를 제출 위치에 설치하고 이전 제출본을 보존한다."""
from pathlib import Path
from datetime import datetime,timezone
import json,shutil,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.review_submission_bundle import verify_directory
P=ROOT/'outputs/private';W=P/'evening_refinement_20261106'
CURRENT=P/'competition_submission';BACKUP=P/'competition_submission_before_field_plan_20261106';STAGE=W/'release'
def read(p):return json.loads(p.read_text('utf8'))
def main():
    final=read(W/'submission_receipt.json');baseline=read(W/'baseline_receipt.json')
    assert final['status']=='two_channel_archives_verified' and final['extracted_field_comparison_reproduced'] and final['extracted_fixed_rule_metrics_reproduced']
    assert not STAGE.exists() and not BACKUP.exists()
    for path in [CURRENT,BACKUP,STAGE]:assert path.resolve().is_relative_to(P.resolve())
    for kind,name in final['archive_filenames'].items():
        assert sha(CURRENT/name)==baseline['archives'][kind]['sha256']
        assert sha(W/name)==final['archives'][kind]['sha256']
    STAGE.mkdir()
    for folder in ['icy_road_model','icy_road_documents']:
        shutil.copytree(W/folder,STAGE/folder,ignore=shutil.ignore_patterns('local_review','__pycache__','*.pyc'))
        verify_directory(STAGE/folder)
    for name in final['archive_filenames'].values():shutil.copy2(W/name,STAGE/name)
    shutil.copy2(W/'submission_receipt.json',STAGE/'submission_receipt.json')
    (STAGE/'README.md').write_text('''# 로드투인사이트 제출 자료

결과제출 화면에서 다음 두 ZIP을 각각 선택한다. 각 ZIP에는 한 개의 최상위 폴더가 들어 있다.

| 제출 항목 | 파일 | 내용 |
| --- | --- | --- |
| 문서자료 | [로드투인사이트_문서자료.zip](로드투인사이트_문서자료.zip) | 13쪽 분석 보고서, 2쪽 현장 확인 계획, 근거 도표·원표, AI 활용 내역 |
| 모델자료 | [로드투인사이트_모델자료.zip](로드투인사이트_모델자료.zip) | 실행 매뉴얼·코드·모형·학습 및 추론 자료·Notebook·전체 CSV/GIS·오프라인 지도·84초 실제 실행 영상 |

[분석 보고서](icy_road_model/report/analysis_report.pdf) · [기상 지도](icy_road_model/index.html) · [구간 검토](icy_road_model/maps/sections.html) · [현장 확인 계획](icy_road_model/results/field/index.html) · [실행 영상](icy_road_model/demo/index.html) · [모델 실행 안내](icy_road_model/README.md)

마감은 2026년 11월 6일 23:59 KST다. 업로드 진행 중에는 창을 닫거나 새로고침하지 말고 접수 이력의 완료 상태를 확인한다. 공식 공통 Q&A 811은 마지막 제출물을 평가한다고 안내한다. 실제 업로드와 제출 버튼 클릭은 수행하지 않았다.

[업로드 주의 안내](https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=807) · [최종 제출물 안내](https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=811)

공식 공지·공통 Q&A 목록은 오늘 19:27 KST에 다시 확인했다. 새 계정 상태 관련 미답변 문의가 목록에 추가됐다. 전체 과제 Q&A와 공통 답변의 본문을 마지막으로 확인한 시각은 15:35 KST이며 이후 상세 본문은 연결 오류로 재확인하지 못했다. 재확인 범위와 한계를 모델자료 technical/official_evening_access_review.json에 기록했다.

파일 무결성, 압축 해제 후 예제 144행의 정확한 추론, 계측 계획과 고정 규칙 비교의 재집계 통과 근거는 submission_receipt.json에 있다. 현장 기록 양식은 미측정 상태다.
''','utf8')
    CURRENT.rename(BACKUP)
    try:STAGE.rename(CURRENT)
    except BaseException:BACKUP.rename(CURRENT);raise
    for kind,name in final['archive_filenames'].items():
        assert sha(CURRENT/name)==final['archives'][kind]['sha256']
        assert sha(BACKUP/name)==baseline['archives'][kind]['sha256']
    for folder in ['icy_road_model','icy_road_documents']:verify_directory(CURRENT/folder)
    result=dict(status='installed_verified',path=str(CURRENT),backup=str(BACKUP),
        files={k:str(CURRENT/n) for k,n in final['archive_filenames'].items()},
        bytes={k:v['bytes'] for k,v in final['archives'].items()},
        sha256={k:v['sha256'] for k,v in final['archives'].items()},
        main_report_pages=13,field_plan_pages=2,demo_seconds=final['demo_seconds'],
        competition_submitted=False,at_utc=datetime.now(timezone.utc).isoformat())
    (W/'installed_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
