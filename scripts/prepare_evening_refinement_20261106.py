"""검증된 제출본을 보존하고 계측 설계와 사용성 보완을 별도 작업 폴더에서 진행한다."""
from pathlib import Path
from datetime import datetime, timezone
import json, shutil

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'outputs/private/competition_submission'
OUT=ROOT/'outputs/private/evening_refinement_20261106'

def main():
    assert not OUT.exists()
    OUT.mkdir()
    shutil.copy2(SOURCE/'submission_receipt.json',OUT/'baseline_receipt.json')
    for name in ['icy_road_model','icy_road_documents']:
        shutil.copytree(SOURCE/name,OUT/name,ignore=shutil.ignore_patterns('local_review','__pycache__','*.pyc'))
    plan=dict(at_utc=datetime.now(timezone.utc).isoformat(),
        objectives=['동일 기상 입력을 공유하는 인접 비선정 구간과의 비교 계측 설계',
                    '두 선정 범위의 근거·위치 한계·측정 항목을 한 화면과 인쇄물에 연결',
                    '빈 현장 기록 양식을 오프라인 저장하고 근거 CSV로 내보내는 동작 검증'],
        control_rule=dict(same_route=True,same_direction=True,same_information_groups_both_winters=True,
            minimum_condition_availability=.95,reference_selected=False,requires_estimated_chainage=True,
            maximum_midpoint_distance_m=2000,selection='nearest midpoint to the area representative midpoint',
            interpretation='기준 미선정 비교 후보이며 안전 구간·실제 비교 계측·확정 설치 위치가 아님'),
        do_not_change=['학습 모형','학습 자료','필수 관측·예측 값','기존 3구간·2범위 선정 기준'],
        sources=[
            dict(title='RoadSurf 1.1',url='https://gmd.copernicus.org/articles/17/4837/2024/gmd-17-4837-2024.html',
                 applied='노면온도와 도로 위 물·얼음·적설을 구별하고 실제 수분·제빙 기록의 필요성을 설명'),
            dict(title='FHWA 도로기상 성과관리',url='https://ops.fhwa.dot.gov/publications/fhwahop20051/index.htm',
                 applied='의사결정 목적, 자료의 해상도·가용성, 추가 수집이 필요한 기록을 연결'),
            dict(title='Vaisala Xweather Horizon 사용자 안내',url='https://guide.wxhorizon.vaisala.com/en-US/using_the_dashboard.html',
                 applied='노선·기간 요약에서 지도 상세와 확인 행동으로 이어지는 정보 순서'),
            dict(title='Anthropic Frontend Design',url='https://github.com/anthropics/skills/tree/main/skills/frontend-design',
                 applied='실제 도로 지도와 이정을 중심으로 한 위계, 구체적인 동작명, 빈 상태의 안내')],
        protected_labels_read_for_this_refinement=False,new_models_planned=False,
        competition_submitted=False)
    (OUT/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n','utf8')
    print('보존된 제출본에서 계측 설계 보완 폴더를 준비했습니다.',flush=True)

if __name__=='__main__':main()
