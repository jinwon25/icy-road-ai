"""검증한 두 제출 ZIP과 열람용 폴더를 최종 제출 위치에 설치한다."""
from pathlib import Path
from datetime import datetime, timezone
import json, shutil, sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.review_submission_bundle import verify_directory

P=ROOT/'outputs/private'
W=P/'judging_upgrade_20261106'
CURRENT=P/'competition_submission'
BACKUP=P/'competition_submission_before_team_final_20261106'
STAGE=W/'release'

def main():
    receipt=json.loads((W/'submission_receipt.json').read_text('utf8'))
    original=json.loads((W/'original_submission_receipt.json').read_text('utf8'))
    assert receipt['status']=='two_channel_archives_verified'
    assert receipt['extracted_model_inference_rows_exact']==144
    assert not STAGE.exists() and not BACKUP.exists()
    for path in [CURRENT,BACKUP,STAGE]:
        assert path.resolve().is_relative_to(P.resolve())
    for kind,name in receipt['archive_filenames'].items():
        assert sha(W/name)==receipt['archives'][kind]['sha256']
        assert sha(CURRENT/f'icy_road_{kind}.zip')==original['archives'][kind]['sha256']
    STAGE.mkdir()
    for name in ['icy_road_model','icy_road_documents']:
        shutil.copytree(W/name,STAGE/name,ignore=shutil.ignore_patterns('local_review','__pycache__','*.pyc'))
        verify_directory(STAGE/name)
    for name in receipt['archive_filenames'].values():
        shutil.copy2(W/name,STAGE/name)
    shutil.copy2(W/'submission_receipt.json',STAGE/'submission_receipt.json')
    (STAGE/'README.md').write_text('''# 로드투인사이트 제출 자료

결과제출 화면에서 다음 두 파일을 각각 선택한다. 두 ZIP은 각각 한 개의 최상위 폴더로 구성했다.

| 제출 항목 | 파일 | 주요 내용 |
| --- | --- | --- |
| 문서자료 | [로드투인사이트_문서자료.zip](로드투인사이트_문서자료.zip) | 13쪽 보고서, 근거 도표, 기준표, 현장 확인표, AI 활용 내역 |
| 모델자료 | [로드투인사이트_모델자료.zip](로드투인사이트_모델자료.zip) | 실행 매뉴얼, 코드, 모형, 학습·추론 자료, Notebook, 전체 결과·GIS, 오프라인 지도, 실행 영상 |

[분석 보고서](icy_road_model/report/analysis_report.pdf) · [기상 지도](icy_road_model/index.html) · [구간 검토](icy_road_model/maps/sections.html) · [실행 영상](icy_road_model/demo/index.html) · [모델 실행 안내](icy_road_model/README.md)

마감은 2026년 11월 6일 23:59 KST다. 업로드 진행 중에는 창을 닫거나 새로고침하지 말고 접수 이력의 완료 상태를 확인한다. 공식 공통 Q&A 811은 마지막 제출물을 평가한다고 안내한다. 실제 사이트 업로드와 제출 버튼 클릭은 수행하지 않았다.

[업로드 주의 안내](https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=807) · [최종 제출물 안내](https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=811)

전체 과제 Q&A와 최신 공통 공지의 본문을 마지막으로 확인한 시각은 오늘 15:35 KST다. 이후 재접속은 연결 오류로 본문을 다시 확인하지 못했다. 파일 무결성·압축 해제·예제 144행의 실제 추론 검증은 submission_receipt.json에 기록했다.
''',encoding='utf8')
    CURRENT.rename(BACKUP)
    try:
        STAGE.rename(CURRENT)
    except BaseException:
        BACKUP.rename(CURRENT)
        raise
    for kind,name in receipt['archive_filenames'].items():
        assert sha(CURRENT/name)==receipt['archives'][kind]['sha256']
        assert sha(BACKUP/f'icy_road_{kind}.zip')==original['archives'][kind]['sha256']
    for name in ['icy_road_model','icy_road_documents']:
        verify_directory(CURRENT/name)
    installed=dict(status='installed_verified',path=str(CURRENT),backup=str(BACKUP),
        archives={k:str(CURRENT/n) for k,n in receipt['archive_filenames'].items()},
        sha256={k:v['sha256'] for k,v in receipt['archives'].items()},
        competition_submitted=False,at_utc=datetime.now(timezone.utc).isoformat())
    (W/'installed_receipt.json').write_text(json.dumps(installed,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(installed,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
