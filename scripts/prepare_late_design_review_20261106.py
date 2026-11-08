"""검증 제출본을 보존하고 마지막 내용·표현 검토를 독립 작업본에 준비한다."""
from pathlib import Path
import shutil,json,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
P=ROOT/'outputs/private';W=P/'late_research_design_20261106';CURRENT=P/'competition_submission'
def main():
    assert not W.exists();W.mkdir()
    shutil.copy2(CURRENT/'submission_receipt.json',W/'baseline_receipt.json')
    for folder in ['icy_road_model','icy_road_documents']:
        shutil.copytree(CURRENT/folder,W/folder,ignore=shutil.ignore_patterns('local_review','__pycache__','*.pyc'))
    before=W/'before_design';before.mkdir()
    for name in ['README.md','demo/index.html','demo/inference.html','report/analysis_report.pdf']:
        target=before/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(CURRENT/'icy_road_model'/name,target)
    plan=dict(at_utc=datetime.now(timezone.utc).isoformat(),audience='과제 심사자와 도로 관리 실무자',
        primary_tasks=['첫 화면에서 대상·성과·한계를 파악','보고서 질문별 페이지로 이동','영상의 필요한 장면만 재생','원표·실행 명령으로 확인'],
        design='전북의 실제 도로와 두 겨울의 비교를 중심으로 한 분석 열람 화면. 장식용 카드·새 위험등급·검증되지 않은 운영 성과를 추가하지 않음.',
        tokens={'ink':'#243640','blue':'#29546d','road_gray':'#bfccd3','amber':'#95652f','paper':'#ffffff','line':'#d5dfe5'},
        type='오프라인 한국어 열람을 위한 맑은 고딕. 본문 15-16px, 제목 28-34px, 표의 숫자는 고정폭 정렬.',
        references=['https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md',
            'https://analysisfunction.civilservice.gov.uk/policy-store/data-visualisation-charts/',
            'https://design.education.gov.uk/design-system/patterns/charts'],
        original_archives_preserved=True,competition_submitted=False)
    (W/'design_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n','utf8')
    print('Prepared independent late review',flush=True)
if __name__=='__main__':main()
