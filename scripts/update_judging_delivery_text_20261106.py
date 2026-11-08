"""사용자에게 보이는 문서와 Notebook을 현재 결과와 실행 경로로 정리한다."""
from pathlib import Path
import sys,json,nbformat
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W
B=W/'icy_road_model'

def main():
    index=B/'index.html';text=index.read_text('utf8')
    marker='<section class="analysis"><h2>결빙 판정과 관측 결빙일</h2>'
    assert text.count(marker)==1 and 'id="benchmarks"' not in text
    section='''<section class="analysis" id="benchmarks"><h2>단순 관측소 기준보다 얼마나 나아졌는가</h2><p class="lead">공통 관측쌍에서 기본 12특성 회귀 대비 노면온도 MAE가 14.6% 낮았습니다. 세 지점 모두 개선됐고, 관측 -2~+2°C 범위에서도 11.4% 낮았습니다.</p><img src="report/figures/temperature_benchmarks.png" alt="같은 관측쌍의 노면온도 MAE 비교. 전체 범위에서 ASOS 기온 2.317, AWS 우선 기온 2.852, ASOS 지면온도 2.157, 기본 회귀 1.146, 현재 회귀 0.978도"><p class="caption">세 지점 동일 가중 평균. 모든 방법에 유효한 103,131쌍과 관측 -2~+2°C의 23,545쌍을 각각 비교했습니다. 앞의 주평가와 공통 쌍의 분모가 다릅니다.</p><p>겨울별 7일 날짜 블록을 함께 재표본화한 2,000회 비교에서 현재 모형과 기본 회귀의 MAE 차이는 -0.202~-0.135°C 범위였습니다. 해당 세 지점·두 겨울의 날짜 민감도이며 새 도로 전체의 보장 범위는 아닙니다.</p><div class="actions"><a href="results/evaluation/temperature_benchmarks/metrics.csv" download>지점·겨울별 비교 CSV</a><a href="results/evaluation/temperature_benchmarks/paired_day_block_sensitivity.csv" download>날짜 블록 민감도</a></div></section>'''
    text=text.replace(marker,section+marker)
    old='조건이 겹치는 500m 22구간을 방향별 11개 연속 범위로 묶었습니다. 현장의 수분·배수·시설 범위를 확인할 후보이며 위험이 입증된 새 지정 구간은 아닙니다.'
    new='기준 조합에서는 500m 22구간을 방향별 11개 범위로 묶었습니다. 기상·선형·목록 경계의 75개 조합에서는 0~86구간으로 달라집니다. 지도에서 기준을 바꾸고 지형 차폐 정보와 함께 현장 확인 근거를 살펴볼 수 있습니다.'
    assert old in text;text=text.replace(old,new).replace('구간과 선정 근거 확인','기준을 바꾸며 구간 검토')
    index.write_text(text,'utf8')
    (B/'README.md').write_text('''# 전북 고속도로 겨울철 분석

센서가 없는 도로의 기상과 노면온도를 추정하고, 추가 계측·시설 확인이 필요한 범위를 검토했다. 대상은 서해안·통영-대전·호남의 500m 843구간과 2024/25·2025/26 두 겨울이다.

## 완성물 확인

[기상 지도](index.html)에서 도로별 두 겨울의 기상과 일별 변화를 비교한다. [구간 검토](maps/sections.html)에서는 기상·선형·목록 경계 기준을 바꾸거나 숫자 행렬을 눌러 선정 범위를 확인한다. [분석 보고서](report/analysis_report.pdf)는 방법·수치·해석을, [실행 영상](demo/index.html)은 실제 탐색과 로컬 모형 추론을 보여준다.

| 항목 | 결과 | 평가 범위 |
| --- | --- | --- |
| 노면온도 | 지점 평균 MAE 0.978°C | 학습 제외 3지점, 103,659 유효쌍 |
| 기존 회귀와 비교 | 기본 12특성 회귀 대비 MAE 14.6% 감소 | 공통 103,131쌍. 관측 -2~+2°C에서는 11.4% 감소 |
| 기온·습도·풍속 | MAE 1.324°C·5.687%p·0.500m/s | 개발 4지역의 지역 전체 제외 평가 |
| 결빙 판정 | Precision 0.0195·Recall 0.5936·F1 0.0326 | 실제 Ice가 있는 부곡교의 날짜별 평균 |
| 계측·시설 확인 | 기준 조합 22구간, 방향별 11개 범위 | 75개 기준 조합에서는 0~86구간 |
| 지형·일사 맥락 | 843중점의 DSM 표고·지평선·하늘 개방도·낮 차폐 | 공개 GLO-30 원본과 1km/3km 탐색 비교 |

기온·습도·풍속의 지정 검증 3지점 실측은 제공 원본에서 모두 결측이었다. 해당 성능은 NA로 남기고 별도 지역 제외 평가와 구분했다. 실제 예측 103,680행과 지점·겨울별 가용성 표를 제공한다.

결빙은 오경보가 많아 단독 경보로 사용하기 어렵다. 선정 기준과 지형 맥락을 실제 Ice의 확률·공식 위험등급으로 바꾸지 않았다. 전체 기상 입력 그룹은 겨울별 68개이며 기준 조합의 22구간은 5개 그룹을 공유한다.

## 결과의 근거

[노면온도 비교](results/evaluation/temperature_benchmarks/metrics.csv)는 ASOS 기온·AWS 우선 기온·ASOS 지면온도·기본 회귀·현재 회귀를 같은 관측쌍에서 비교한다. 세 지점 모두 기본 회귀보다 MAE가 낮았다. 7일 날짜 블록 민감도와 관측 -2~+2°C 부분집합도 포함한다.

[선정 민감도](results/sections/sensitivity/scenario_summary.csv)는 상위 기상 빈도와 선형 변화 기준, 공개 목록의 위치 여유를 바꾼 75개 조합이다. F06의 두 구간은 60개 조합에서 유지됐다. 이는 현장 확인 순서의 참고 근거이며 결빙이 가장 많은 곳이라는 검증은 아니다.

[기상·조건 연관성](results/conditions/segment_daily_associations.csv)은 202,320개 일별 추정 자료에서 계산했다. 실제 Ice의 조건별 분포는 개발 9지점 309,928개 유효쌍으로 별도 제시한다. 추정값끼리의 연관성과 실측 Ice의 빈도, 인과효과를 구분했다.

개발 9지점의 오경보 25,341건 중 94.3%는 실제 노면온도도 영하였고 98.8%는 주변 ASOS 적설을 근거로 포함했다. [노면상태 분해](results/evaluation/development_false_alarm_states.csv)와 [수분 근거](results/evaluation/development_moisture_evidence.csv)는 보호 지점 평가와 별도인 개발 진단이다.

## 환경과 추론

Python 3.11·CPU에서 실행한다. 버전은 requirements.txt에 고정했다. Chrome 또는 Edge에서 index.html을 직접 열 수 있다. 추론에는 API 인증정보가 필요하지 않다.

    python -m pip install -r requirements.txt
    python code/predict.py --input data/weather_example.csv --output local_review/road_predictions.csv --output-start 2024-12-15 --output-end 2024-12-16
    python code/predict_weather.py --input data/weather_context_example.csv --aws-input data/aws_example.parquet --points data/points_example.csv --output local_review/weather_predictions.csv --output-start 2024-12-15 --output-end 2024-12-16

첫 명령은 노면온도와 결빙 조건, 둘째는 기온·습도·풍속을 산출한다. 이력 모형에는 출력일 전 24시간의 문맥을 함께 입력한다. 기존 출력은 덮어쓰지 않는다. 기온 0°C 기준선은 첫 명령에 --method air_temperature를 지정한다.

## 근거 계산 재현

다음 명령은 포함 자료를 다시 계산하며 모형을 학습하거나 문턱을 선택하지 않는다. 각 출력 폴더는 새 경로를 사용한다.

    python code/analyze_temperature_benchmarks.py --output local_review/temperature_comparison
    python code/analyze_inspection_sensitivity.py --output local_review/criteria_comparison
    python code/analyze_segment_conditions.py --output local_review/condition_analysis
    python code/analyze_icing_errors.py --output local_review/icing_error_analysis

공개 DSM 네 타일을 포함했으므로 지형 계산도 오프라인으로 재현할 수 있다. 이 단계만 추가 지리 라이브러리가 필요하다.

    python -m pip install -r requirements-geospatial.txt
    python code/derive_terrain_context.py --output local_review/terrain_analysis

[분석 Notebook](notebooks/analysis.ipynb)은 현재 수치와 실제 추론·재집계를 연결한다. [학습 Notebook](notebooks/training.ipynb)과 다음 명령은 포함 학습 자료로 모형을 재학습한다.

    python code/train.py --output local_review/trained_model

기온·습도·풍속 재학습은 weather/의 목적별 안내를 따른다.

## 자료 구성과 범위

- results/evaluation/: 필수 관측·예측 표, 날짜·지점 지표, 노면온도 비교와 기상 가용성
- results/weather/: 500m 겨울·일별 기상 CSV·Parquet·GIS
- results/conditions/: 추정 기상·조건의 연관성과 개발 지점 실제 Ice의 조건별 분포
- results/sections/: 선정 기준·11개 범위·75개 조합·지형 맥락·Shapefile·GeoPackage
- results/inventory/: 공개 취약구간과의 관계 및 이정 민감도
- model/, data/, code/, src/: 학습된 모형·학습 자료·공개 지형 원본·실행 코드
- technical/, validation/: 입력·출처·실행 검증 근거
- licenses/, [AI 활용 내역](AI_USAGE.md): 이용조건과 개발 지원 범위

필수 제출 표는 [observations_predictions.csv](results/evaluation/observations_predictions.csv)다. 고속도로명·지점명·정확한 10분 KST 시각·관측 노면상태·결빙 예측·관측 노면온도·추정 노면온도를 포함한다. 원 관측 누락 3행과 추론 결측 18행을 유지했다.

DSM은 수목·시설물을 포함하며 교량 상판 고도나 터널 내부를 측량한 자료가 아니다. 낮의 지형 차폐는 실제 일조·일사량 관측이나 위험 가중치로 해석하지 않는다. 두 겨울은 10년 기후를 대체하지 않는다. 제공 자료는 승인된 대회 심사용이며 공개 재배포를 전제로 하지 않는다.
''','utf8')
    (B/'AI_USAGE.md').write_text('''# AI 활용 내역

AI는 기상·도로 자료 처리, 학습·검증 코드 작성과 점검, 공식 공지·질의응답 대조, 결과 해석과 문서 조판, 오프라인 화면과 실행 영상 제작을 지원했다. 제출물의 수치는 실제 로컬 계산과 실행 결과에서 가져왔다. 보호 지점의 관측값은 고정 예측과의 대조에 사용했으며 신규 학습·임계값 조정에 사용하지 않았다.

추가 후보가 정밀도·F1·재현율과 결빙 사건 보존 조건을 함께 충족하지 못해 기존 판정 모형을 유지했다. 현재 분석은 노면온도 비교, 오경보의 실제 상태 분포, 선정 기준 민감도와 지형 맥락을 함께 제시한다. AI가 작성한 설명 자체를 성능 입증으로 취급하지 않는다.

표현과 검토 절차에는 공개 Anthropic Frontend Design 스킬, Scientific Agent Skills의 Scientific Critical Thinking·Scientific Visualization, Codex PDF 스킬을 참고했다. 유효 표본과 분모, 비교 기준, 기술통계와 인과효과의 구분, 실제 크기에서의 도표·PDF 검수를 적용했다.

- Anthropic. Frontend Design: https://github.com/anthropics/skills/tree/main/skills/frontend-design
- Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. https://doi.org/10.48550/arXiv.2609.00065
- Scientific Agent Skills 공개 라이브러리: https://github.com/K-Dense-AI/scientific-agent-skills

이 공개 절차의 사용을 실험 성능 개선이나 입상 가능성이 검증됐다는 근거로 삼지 않았다. 보고서의 물리적 해석과 자료 이용조건은 각각의 원천 문헌·라이선스를 따른다.
''','utf8')
    nbpath=B/'notebooks/analysis.ipynb';nb=nbformat.read(nbpath,as_version=4)
    assert len([c for c in nb.cells if c.cell_type=='code'])==6
    additions=[
        ('같은 관측쌍의 노면온도 비교','다섯 비교 방법의 유효 시각을 맞추고 전체·0°C 부근의 지표를 다시 계산한다. 관측 표를 평가에 사용하며 학습에는 전달하지 않는다.',
'''from src.evidence_analysis import evaluate as regression_evaluate
benchmark=pd.read_parquet(root/'results/evaluation/temperature_benchmarks/observations_predictions.parquet')
methods={'asos_air_reference':'asos_air_temperature','aws_air_reference':'aws_air_temperature','asos_ground_reference':'asos_ground_temp','weather12_regression':'reference_temperature_12','estimated':'estimated_road_temperature_c'}
rows=regression_evaluate(benchmark,'observed_road_temperature_c',methods)
computed=pd.DataFrame(rows)
expected=pd.read_csv(root/'results/evaluation/temperature_benchmarks/metrics.csv',dtype={'station':str})
expected=expected.loc[expected.temperature_scope.eq('all_temperature')].drop(columns='temperature_scope').reset_index(drop=True)
pd.testing.assert_frame_equal(computed[expected.columns],expected,check_dtype=False,atol=1e-12,rtol=1e-12)
display(computed.loc[computed.period.eq('all')&computed.station.eq('station_macro'),['method','n','mae','bias','rmse']])
display(Image(filename=str(root/'report/figures/temperature_benchmarks.png')))'''),
        ('선정 기준 75개 조합','선택 유지율은 사전 명시한 자체 기준 조합에서 선택된 비율이며 실제 결빙확률이 아니다.',
'''from src.inspection_sensitivity import inspection_scenario
sections=pd.read_csv(root/'results/sections/section_review.csv',dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
overlap=pd.read_csv(root/'results/inventory/overlap_sensitivity.csv',dtype={'seg_id':str},float_precision='round_trip')
base,_=inspection_scenario(sections,overlap)
assert base.selected.sum()==22
scenarios=pd.read_csv(root/'results/sections/sensitivity/scenario_summary.csv')
for r in scenarios.itertuples():
    census,_=inspection_scenario(sections,overlap,r.weather_quantile,r.curve_quantile,r.margin_m)
    assert census.selected.sum()==r.selected_segments
display(pd.read_csv(root/'results/sections/sensitivity/area_stability.csv'))
display(Image(filename=str(root/'report/figures/selection_sensitivity.png')))'''),
        ('추정 기상과 실제 Ice의 조건 분포','구간별 추정 연관성, 개발 지점의 실제 Ice 빈도, 인과효과를 구분한다. 미관측 지점의 실측 기상은 결측이다.',
'''availability=pd.read_csv(root/'results/evaluation/protected_weather/target_availability.csv')
assert availability[['air_temperature','relative_humidity','wind_speed']].eq(0).all().all()
association=pd.read_csv(root/'results/conditions/segment_daily_associations.csv')
assert len(association)==20232 and association.daily_pairs.le(120).all()
conditions=pd.read_csv(root/'results/conditions/development_observed_ice_by_condition.csv')
assert conditions.valid_pairs.sum()==309928 and conditions.observed_ice_pairs.sum()==6687
display(conditions)
display(Image(filename=str(root/'report/figures/observed_ice_conditions.png')))'''),
        ('지형·일사 맥락','공개 DSM 원본과 지형·태양위치 코드를 포함한다. 1km/3km의 차폐를 비교하며 실제 일조·위험 가중치로 해석하지 않는다.',
'''terrain=pd.read_csv(root/'results/sections/terrain/segment_terrain.csv',dtype={'seg_id':str})
solar=pd.read_csv(root/'results/sections/terrain/segment_solar_context.csv',dtype={'seg_id':str})
assert len(terrain)==843 and len(solar)==1686
assert solar.potential_shade_daylight_fraction.ge(solar.potential_shade_daylight_fraction_1km-1e-12).all()
display(terrain[['dsm_elevation_m','sky_view_proxy','horizon_max_deg']].describe())
display(Image(filename=str(root/'report/figures/terrain_solar_context.png')))''')]
    for title,description,code in additions:
        nb.cells.extend([nbformat.v4.new_markdown_cell('## '+title+'\n\n'+description),nbformat.v4.new_code_cell(code)])
    for c in nb.cells:
        if c.cell_type=='code':c.outputs=[];c.execution_count=None
    nbformat.validate(nb);nbformat.write(nb,nbpath)
    print('최종 README·AI 활용 내역과 분석 Notebook 10개 코드 셀 정리 완료',flush=True)

if __name__=='__main__':main()
