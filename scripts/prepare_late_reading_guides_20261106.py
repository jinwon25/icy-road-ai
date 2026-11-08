"""루트 안내를 최종 결과 요약에서 시작하도록 정리하고 기존 원문을 보존한다."""
from pathlib import Path
import json,shutil
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/late_research_design_20261106'
def main():
    before=W/'root_documents_before';after=W/'current_project_documents';before.mkdir();after.mkdir()
    names=['README.md','docs/START_HERE.md','docs/STATUS.md']
    for name in names:
        p=before/name;p.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(ROOT/name,p)
    s=(ROOT/'README.md').read_text('utf8')
    old='[분석 화면](outputs/private/competition_submission/icy_road_model/index.html)';assert s.count(old)==1
    s=s.replace(old,'[결과 요약](outputs/private/competition_submission/icy_road_model/start.html) · [기상 지도](outputs/private/competition_submission/icy_road_model/index.html)')
    s=s.replace('[AI 활용 내역](AI_USAGE.md)','[AI 활용 내역](outputs/private/competition_submission/icy_road_model/AI_USAGE.md)')
    (after/'README.md').write_text(s,'utf8')
    s='''# 분석 결과 읽는 순서

1. [결과 요약](../outputs/private/competition_submission/icy_road_model/start.html)에서 분석 범위·온도 성과·결빙의 한계·추가 계측 범위를 확인한다. 각 결과는 비교 원표와 보고서 해당 쪽으로 연결된다.
2. [14쪽 보고서](../outputs/private/competition_submission/icy_road_model/report/analysis_report.pdf)의 질문별 링크와 책갈피에서 필요한 부분을 읽는다.
3. [기상 지도](../outputs/private/competition_submission/icy_road_model/index.html)와 [구간 검토](../outputs/private/competition_submission/icy_road_model/maps/sections.html)에서 노선·겨울·변수·기준을 바꿔 대조한다.
4. [실행 영상](../outputs/private/competition_submission/icy_road_model/demo/index.html)의 8개 장면 중 필요한 부분을 재생하고, [실행 안내](../outputs/private/competition_submission/icy_road_model/README.md)의 전체 기간 재현 명령을 확인한다.
5. [현장 확인 계획](../outputs/private/competition_submission/icy_road_model/results/field/index.html)에서 두 범위의 위치·인접 비교 후보·측정 항목을 확인한다. 미측정 기록 양식과 인쇄용 계획서를 제공한다.

노면온도 MAE는 학습 제외 3지점 평균 0.978°C, 결빙 F1은 실제 Ice가 있는 1지점의 날짜별 평균 0.0326이다. 정밀도가 낮아 경보 성능에는 한계가 남는다. 실제 기상 입력의 중복을 합친 기준 조합은 3구간·2개 범위다. 선정 민감도를 함께 제공하며 추가 계측·시설 확인 자료로 사용한다.
'''
    (after/'START_HERE.md').write_text(s,'utf8')
    s=(ROOT/'docs/STATUS.md').read_text('utf8');old='[분석 보고서]';assert old in s
    s=s.replace(old,'[결과 요약](../outputs/private/competition_submission/icy_road_model/start.html) · '+old,1)
    (after/'STATUS.md').write_text(s,'utf8')
    note=(ROOT/'outputs/private/competition_submission/JURY_REVIEW.md').read_text('utf8')
    note+='''

## 열람 구성과 추가 검토

[결과 요약 화면](icy_road_model/start.html)은 온도 성과와 낮은 결빙 정밀도, 계측 후보를 함께 보여 준다. 도표는 비교 분모와 원표를 연결한다. 영상은 실제 미리보기와 8개 장면 이동, 문자 설명을 제공한다. 보고서는 14개 책갈피와 질문별 이동 링크 3개를 포함한다. 키보드 노선 선택·영상 이동·표 스크롤과 작은 화면을 실제 브라우저에서 확인했다.

짧은 감쇠 누적은 선행연구의 가설을 현재 허용 기상 입력으로 검토한 반복 개발 실험이다. 실제 노면온도를 쓰는 원 연구와 입력·목표가 다르며, 외부 논문의 성능을 우리 결과로 인용하지 않았다. 채택 여부와 검산은 모델자료 technical의 해당 검토 파일에 기록했다. 결빙 성능의 검증된 개선 없이 수상권이라고 판단하지 않는다.
'''
    (W/'JURY_REVIEW.md').write_text(note,'utf8')
    print('Prepared current reading guides and preserved previous root documents',flush=True)
if __name__=='__main__':main()
