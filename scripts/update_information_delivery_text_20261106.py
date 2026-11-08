"""최종 화면·문서·Notebook의 수치를 현재 3구간과 실제 입력 정보 단위로 맞춘다."""
from pathlib import Path
import sys,json,nbformat
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W
B=W/'icy_road_model'

def main():
    p=B/'index.html';text=p.read_text('utf8')
    old='기준 조합에서는 500m 22구간을 방향별 11개 범위로 묶었습니다.'
    new='실제 입력 시계열의 중복을 제외한 기준 조합에서는 서해안 500m 3구간을 2개 범위로 묶었습니다.'
    assert old in text;text=text.replace(old,new);p.write_text(text,'utf8')
    p=B/'README.md';text=p.read_text('utf8')
    pairs=[
        ('기준 조합 22구간, 방향별 11개 범위','기준 조합 3구간, 서해안 2개 범위'),
        ('전체 기상 입력 그룹은 겨울별 68개이며 기준 조합의 22구간은 5개 그룹을 공유한다.',
         '관측소 후보 조합은 겨울별 68개다. 결빙 조건에 쓰는 14열 전체 시계열의 중복을 합치면 실제 정보는 첫 겨울 22개·둘째 겨울 24개다. 분위수는 이 단위로 계산했다. 선정된 세 구간은 겨울마다 하나의 조건 입력을 공유한다.'),
        ('F06의 두 구간은 60개 조합에서 유지됐다.','S01의 두 구간은 60개 조합(80%), S02의 한 구간은 48개 조합(64%)에서 유지됐다.'),
        ('선정 기준·11개 범위·75개 조합','선정 기준·2개 범위·75개 조합')]
    for a,b in pairs:assert a in text,a;text=text.replace(a,b)
    command='    python code/analyze_inspection_sensitivity.py --output local_review/criteria_comparison'
    assert command in text
    text=text.replace(command,'    python code/rebuild_weather_information.py --output local_review/weather_information\n'+command)
    note='전체 2,350,080행의 실제 조건 입력과 식별자 대조표를 포함했다. 같은 배열은 원소 전체를 비교해 확인했으며, 위 재현 명령은 고정 모형으로 노출의 분자·분모까지 다시 계산한다. [현장 확인표](results/sections/field_review_plan.csv)는 두 범위의 대표 중점과 확인 항목·기록용 빈 열을 제공한다.\n\n'
    marker='공개 DSM 네 타일을 포함했으므로'
    assert marker in text;text=text.replace(marker,note+marker);p.write_text(text,'utf8')
    p=B/'AI_USAGE.md';text=p.read_text('utf8')
    text=text.replace('현재 분석은 노면온도 비교, 오경보의 실제 상태 분포, 선정 기준 민감도와 지형 맥락을 함께 제시한다.',
        '현재 분석은 노면온도 비교, 오경보의 실제 상태 분포, 실제 조건 입력 시계열의 중복 제거, 선정 기준 민감도와 지형 맥락을 함께 제시한다.')
    p.write_text(text,'utf8')
    p=B/'notebooks/analysis.ipynb';nb=nbformat.read(p,as_version=4)
    for cell in nb.cells:
        if cell.cell_type=='code':
            cell.source=cell.source.replace('len(areas)==11 and areas.segments.sum()==22','len(areas)==2 and areas.segments.sum()==3')
            cell.source=cell.source.replace('base.selected.sum()==22','base.selected.sum()==3')
            if 'from src.inspection_sensitivity import' in cell.source:
                cell.source="information=pd.read_csv(root/'data/weather_information_groups.csv')\nassert information.groupby('winter').weather_information_group.nunique().to_dict()=={2024:22,2025:24}\n"+cell.source
            cell.execution_count=None;cell.outputs=[]
        elif '## 추가 계측·시설 확인' in cell.source:
            cell.source+=' 결빙 조건의 실제 14입력 시계열이 같은 조합은 한 번만 집계한다. 현재 기준 조합은 서해안 3구간·2개 범위다.'
    nbformat.validate(nb);nbformat.write(nb,p)
    f=pd.read_csv(B/'results/sections/section_review.csv',dtype={'seg_id':str},float_precision='round_trip')
    terrain=pd.read_csv(B/'results/sections/terrain/segment_terrain.csv',dtype={'seg_id':str},float_precision='round_trip').set_index('seg_id')
    stability=pd.read_csv(B/'results/sections/sensitivity/area_stability.csv').set_index('inspection_area_id')
    rows=[]
    for area,q in f.loc[f.inspection_candidate].groupby('inspection_area_id'):
        first=q.loc[q.winter.eq(2024)].sort_values('estimated_km_lo').iloc[0];t=terrain.loc[first.seg_id]
        rows.append(dict(area_id=area,route=first.route_nm,direction=first.flow_lbl,
            estimated_km_start=q.estimated_km_lo.min(),estimated_km_end=q.estimated_km_hi.max(),
            representative_midpoint_lat=t.point_lat,representative_midpoint_lon=t.point_lon,
            segments=q.seg_id.nunique(),minimum_selection_fraction=stability.loc[area,'minimum_selection_fraction'],
            maximum_selection_fraction=stability.loc[area,'maximum_selection_fraction'],
            weather_information_groups_2024=q.loc[q.winter.eq(2024),'weather_information_group'].nunique(),
            weather_information_groups_2025=q.loc[q.winter.eq(2025),'weather_information_group'].nunique(),
            field_confirmation='대표 중점과 실제 도로 구조·배수·노면수분·염분·제설 시각을 함께 확인',
            measured_at_kst='',observed_road_temperature_c='',observed_moisture_state='',residual_salt='',last_treatment_time_kst='',observed_shade='',notes='',
            official_location_verified=False))
    pd.DataFrame(rows).to_csv(B/'results/sections/field_review_plan.csv',index=False,encoding='utf-8-sig')
    p=B/'technical/competition_requirements.md'
    p.write_text('''# 과제 요구와 자료 위치

공통 문제해결 평가 기준은 창의성 20·우수성 50·효과성 30이다. 과제의 세부 산출물에 임의 배점을 붙이거나 입상 점수를 계산하지 않았다.

| 과제 요구 | 현재 자료 |
| --- | --- |
| 고속도로·지점·정확한 10분 시각의 관측·추정 | ../results/evaluation/observations_predictions.csv |
| BIAS·MAE·RMSE와 날짜→지점 Precision·Recall·F1 | ../results/evaluation/ 및 ../report/analysis_report.pdf |
| 학습 제외 지점과 비교 기준의 수치 대조 | ../results/evaluation/temperature_benchmarks/ |
| 지정 지점 기상 추정과 결측의 명시 | ../results/evaluation/protected_weather/ |
| AI 추정 기상·결빙 조건의 연관성과 조건별 실측 Ice | ../results/conditions/ |
| 500m 기준표·지도·공간 파일 | ../results/weather/, ../results/sections/, ../maps/sections.html |
| 실제 정보의 중복 제거와 기준 민감도 | ../data/weather_information_groups.csv, ../results/sections/sensitivity/ |
| 추가 자료의 근거와 지형 한계 | ../results/sections/terrain/, ../data/copernicus_dem/ |
| 학습·추론·재현 코드·자료·모형·Notebook·환경 | ../code/, ../data/, ../model/, ../notebooks/, ../weather/, ../requirements.txt |
| 실제 탐색·추론 영상 | ../demo/index.html |
| AI 활용 및 이용조건 | ../AI_USAGE.md, ../licenses/ |

서약과 공식 Q&A의 무결빙 지점 제외, 지표별 날짜 처리, 다른 지점의 동시 노면상태 입력 금지, 정규화 DEM 단위와 자체 기준의 근거 명시를 적용했다. 현재 기준 조합은 3구간·2개 범위이며 실제 입력의 중복을 제거한 기준이다. 두 겨울을 10년 기후값으로 대체하지 않았다.

[공식 과제](https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do)
''','utf8')
    print('현재 3구간·2개 범위와 실제 입력 정보 단위로 문서·화면·Notebook·현장표 정합화 완료')

if __name__=='__main__':main()
