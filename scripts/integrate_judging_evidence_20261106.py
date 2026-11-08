"""검토가 끝난 신규 근거 자료를 최종 형식의 제출 사본에 배치한다."""
from pathlib import Path
import shutil,json,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W,write
B=W/'icy_road_model';O=B/'results'

def main():
    assert not (B/'technical/judging_evidence.json').exists()
    for source,target in [('terrain_context','sections/terrain'),('condition_evidence','conditions'),('temperature_benchmarks','evaluation/temperature_benchmarks')]:
        shutil.copytree(W/source,O/target)
    weather=W/'protected_weather'
    for name in ['target_availability.csv','metrics.csv','observations_predictions.csv.gz','paired_day_block_sensitivity.csv']:
        target=O/'evaluation/protected_weather'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(weather/name,target)
    shutil.copyfile(weather/'assessment.json',B/'technical/protected_weather_audit.json')
    # 공개 지형 원본 4타일과 원천·이용조건을 함께 포함해 843중점 계산을 오프라인으로 재현한다.
    source=ROOT/'outputs/private/releases/20261007/outputs/private/external/copernicus_dem'
    shutil.copytree(source,B/'data/copernicus_dem')
    shutil.copyfile(ROOT/'src/solar_terrain.py',B/'src/solar_terrain.py')
    shutil.copyfile(ROOT/'src/inspection_sensitivity.py',B/'src/inspection_sensitivity.py')
    (B/'requirements-geospatial.txt').write_text('-r requirements.txt\nrasterio==1.4.4\npyproj==3.7.2\ngeopandas==1.1.3\nshapely==2.1.2\npyogrio==0.12.1\n','utf8')
    # 패키지 안에서는 프로젝트의 과거 실행 경로 대신 최종 상대 경로로 재현한다.
    calendar=pd.read_csv(ROOT/'outputs/private/submission_candidate_20261106_v14/exports/prediction_group_daily.csv',dtype={'prediction_group':str},float_precision='round_trip')
    groups=set(pd.read_csv(O/'sections/section_review.csv',usecols=['prediction_group'],dtype=str).prediction_group)
    calendar.loc[calendar.prediction_group.isin(groups)].to_csv(B/'data/prediction_group_daily.csv.gz',index=False,encoding='utf-8-sig',compression='gzip')
    notice=json.loads((W/'terrain_context/summary.json').read_text('utf8'))['source_notice']
    sources=dict(temperature_benchmarks=json.loads((W/'temperature_benchmarks/summary.json').read_text('utf8')),
        inspection_sensitivity=json.loads((W/'inspection_sensitivity/summary.json').read_text('utf8')),
        terrain_context=json.loads((W/'terrain_context/summary.json').read_text('utf8')),
        protected_weather_available_observation_pairs=0,
        main_models_unchanged=True,official_required_prediction_values_unchanged=True)
    write(B/'technical/judging_evidence.json',sources)
    (O/'conditions/README.md').write_text('''# 기상요소와 조건의 관계

구간별 CSV는 202,320개의 일별 추정 자료에서 계산한 Pearson·Spearman 연관성입니다. 각 겨울·구간에서 최대 120일을 사용하며, 추정 기온·습도·풍속과 추정 노면온도·저온 수분 조건 비율을 대조합니다. 실제 Ice 관측의 인과효과나 새 결빙 임계값으로 해석하지 않습니다. 모형과 판정식이 입력을 공유하므로 연관성에는 계산 구조가 반영됩니다.

개발 지점 조건 표는 지역을 제외한 9지점의 기준온도 추정과 실제 Ice를 사용합니다. 사전 고정한 -2·0·2°C 경계와 수분 대용조건 유무로 나눴습니다. 전체 10분 관측의 빈도이며 공식 날짜별 Precision 평균과 다릅니다. 지점별 표와 동일 가중 평균을 함께 제공해 특정 지점의 많은 관측에 의존하는지 확인할 수 있습니다. 새 판정법의 문턱 선택에는 사용하지 않았습니다.
''','utf8')
    (O/'sections/terrain/README.md').write_text('''# 구간별 지형·일사 맥락

Copernicus GLO-30 공개 DSM의 4타일에서 기상 지도와 같은 843개 구간 중점을 조회했습니다. 표고는 EGM2008 기준 미터이며, 제공된 정규화 DEM과 구별합니다. DSM에는 수목·시설물이 포함됩니다. 도로 상판 높이·도로 경사·터널 내부 형상으로 해석할 수 없습니다.

16방향의 지평선을 60m 간격으로 3km까지 탐색하고 태양위치 근사식과 대조했습니다. 낮의 지형 차폐 가능 비율은 태양 고도가 양수인 10분 시점 가운데 근사 지평선 아래에 놓인 시점의 비율입니다. 1km 탐색도 함께 제공해 공간 범위의 민감도를 확인합니다. 구름·대기·세부 장애물·현장 측정은 포함하지 않습니다. 일조·일사량 관측이나 실제 결빙 확률이 아닙니다.

낮의 일사 차폐와 밤의 복사냉각은 역할이 달라, 이 지표를 위험 배점으로 자동 합산하지 않았습니다. 원래 모형과 기준 조합의 구간 선정도 변경하지 않았습니다. 공개 원본, 라이선스·출처 및 재현 코드를 포함합니다.

'''+notice+'\n\n자료 설명: https://doi.org/10.5270/ESA-c5d3d65\n','utf8')
    (O/'evaluation/protected_weather/README.md').write_text('''# 지정 지점의 기상 추정과 관측 가용성

부곡교·해전·삼봉의 두 겨울 예측 103,680행을 고정한 뒤 제공 원본의 기온·습도·1분 풍속과 대조했습니다. 세 요소의 실제 관측은 세 지점 모두 결측코드로 제공되어 유효 관측쌍이 0개입니다. 성능 지표는 NA이며 기상청 관측소 값을 해당 도로의 실측 정답으로 대체하지 않았습니다.

지정 지점의 노면온도·노면상태 평가와 이 기상 요소의 결측은 서로 다릅니다. 도로 기상 모형의 오차 비교는 별도 지역 제외 평가를 사용합니다. 전체 예측과 지점·겨울별 가용성 표를 포함합니다. 기상 예측 고정 전에도 보호 노면온도·노면상태는 기존 제출 평가에서 열람된 상태였으므로 새 지점 전체가 처음 공개되는 독립 평가라고 부르지 않습니다.
''','utf8')
    print('최종 형식으로 신규 기상·선정 기준·지형·조건 근거 배치 완료')

if __name__=='__main__':main()
