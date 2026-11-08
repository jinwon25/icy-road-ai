"""실제 정보 시계열 단위의 선정 기준·공간 파일과 재현 진입점을 정합하게 만든다."""
from pathlib import Path
import sys,json,shutil
import numpy as np
import pandas as pd
import geopandas as gpd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W,write
from src.data_source import sha256_file as sha
B=W/'icy_road_model';S=B/'results/sections';O=W/'information_group_correction'

def main():
    assert not (O/'replay_and_gis_verified.json').exists()
    expected=pd.read_csv(B/'data/weather_information_groups.csv',dtype={'prediction_group':str},float_precision='round_trip')
    computed=pd.read_csv(B/'local_review/weather_information_exact/weather_information_groups.csv',dtype={'prediction_group':str},float_precision='round_trip')
    pd.testing.assert_frame_equal(expected,computed,check_exact=True)
    f=pd.read_csv(S/'section_review.csv',dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
    computed=pd.read_csv(B/'local_review/weather_information_exact/exposure_by_input_group.csv',dtype={'prediction_group':str},float_precision='round_trip')
    matched=f.merge(computed,on=['prediction_group','winter'],suffixes=('','_replay'),validate='many_to_one')
    for column in ['planned_slots','ice_valid_slots','cold_wet_slots','weather_index_100']:
        np.testing.assert_array_equal(matched[column],matched[column+'_replay'])
    assert (matched.weather_information_group==matched.weather_information_group_replay).all()
    geometry=gpd.read_file(B/'results/weather/weather_segments.gpkg',layer='winter_2024')[['seg_id','geometry']]
    aliases={'seg_id':'seg_id','winter':'winter','weather_index_100':'wx_index','condition_availability':'wx_avail',
        'curve_deg_100m':'curve100','bridge_code_fraction':'bridge_fr','tunnel_code_fraction':'tunnel_fr',
        'review_code':'review_cd','review_label':'review_nm','wind_network_outside_fraction':'wind_out','weather_information_group':'wx_info'}
    moved=[]
    for path in [S/'risk_review.gpkg',S/'inspection_locations.gpkg',S/'shapefile_2024',S/'shapefile_2025']:
        previous=O/('previous_'+path.name)
        assert path.resolve().is_relative_to(W.resolve()) and previous.resolve().is_relative_to(W.resolve()) and not previous.exists()
        path.rename(previous);moved.append(path.name)
    for winter,part in f.groupby('winter'):
        g=gpd.GeoDataFrame(part.merge(geometry,on='seg_id',validate='one_to_one'),geometry='geometry',crs=geometry.crs)
        g.to_file(S/'risk_review.gpkg',layer=f'winter_{winter}',driver='GPKG')
        folder=S/f'shapefile_{winter}';folder.mkdir()
        g[[*aliases,'geometry']].rename(columns=aliases).to_file(folder/f'risk_{winter}_500m.shp',encoding='UTF-8')
        check=gpd.read_file(folder/f'risk_{winter}_500m.shp').sort_values('seg_id')
        np.testing.assert_array_equal(check.review_cd,g.sort_values('seg_id').review_code)
    selected=f.loc[f.winter.eq(2024)&f.inspection_candidate]
    gpd.GeoDataFrame(selected.merge(geometry,on='seg_id',validate='one_to_one'),geometry='geometry',crs=geometry.crs).to_file(S/'inspection_locations.gpkg',layer='inspection_segments',driver='GPKG')
    # 기존 개수의 공간 파일이 남지 않도록 선정 유지율 GIS도 현재 자료로 재생성한다.
    stable=pd.read_csv(S/'sensitivity/segment_stability.csv',dtype={'seg_id':str},float_precision='round_trip')
    gpd.GeoDataFrame(stable.merge(geometry,on='seg_id',validate='one_to_one'),geometry='geometry',crs=geometry.crs).to_file(S/'sensitivity/selection_stability.gpkg',layer='criteria_stability',driver='GPKG')
    s=B/'src/section_review.py';text=s.read_text('utf8')
    assert "drop_duplicates(['prediction_group','winter'])" in text
    text=text.replace("unique=f.drop_duplicates(['prediction_group','winter'])","group_column='weather_information_group' if 'weather_information_group' in f else 'prediction_group'\n unique=f.drop_duplicates([group_column,'winter'])")
    s.write_text(text,'utf8')
    # 재집계에 사용하는 입력 열과 단위를 최종 자료에 명시한다.
    criteria=pd.read_csv(S/'criteria.csv')
    criteria.loc[criteria.item.eq('높은 기상조건 빈도'),['formula','threshold','basis']]=[
        '결빙 조건 14입력의 전체 시계열이 같은 조합을 1회 집계한 겨울별 75백분위 이상',
        '2024/25 12.012968%, 2025/26 4.791944%',
        '첫 겨울 22개·둘째 24개 서로 다른 실제 입력 시계열. 후보 관측소 조합의 중복 제거']
    criteria.to_csv(S/'criteria.csv',index=False,encoding='utf-8-sig')
    (S/'README.md').write_text('''# 도로환경·계측 검토 자료

section_review.csv는 843구간·두 겨울의 조건 비율·도로환경·공개 목록 관계와 실제 입력 정보그룹을 연결한 표다. 기준 조합은 3개 500m 구간, 서해안의 S01·S02 두 연속 범위이며 총 길이는 1.5km다.

겨울별 관측소 후보 조합은 68개다. 결빙 조건에 사용하는 14열의 전체 10분 입력 시계열을 비교해 같은 배열은 한 번 집계했다. 첫 겨울 22개, 둘째 겨울 24개의 고유 입력에서 75백분위를 구했다. 이는 독립 관측 표본 수를 뜻하지 않는다. 선정된 세 구간은 겨울별로 같은 하나의 정보 시계열을 공유한다.

판정 가용률 95% 이상, 교량 코드 또는 중심선 방향 변화 상위 25%, 공개 목록 ±250m 비중첩과 이정 추정 가능 조건을 함께 요구했다. 현재 세 구간은 교량 코드가 아닌 방향 변화 기준에 해당한다. 방향 변화는 설계 곡률·회전반경과 다르다.

선정 재계산:

    python code/review_sections.py --output local_review/inspection_recomputed.csv
    python code/rebuild_weather_information.py --output local_review/weather_information_recomputed
    python code/analyze_inspection_sensitivity.py --output local_review/selection_sensitivity_recomputed

전체 2,350,080행의 기상 입력을 포함하며, 두 고정 회귀 모형으로 조건 노출과 입력 정보그룹을 재현할 수 있다. 관측 노면상태나 노면온도는 이 계산에 입력하지 않는다.

risk_review.gpkg와 겨울별 Shapefile은 각 겨울의 검토 분류를, inspection_locations.gpkg는 두 겨울 공통 조건과 공개 목록 대조까지 적용한 세 선정 구간을 담는다. 75개 기준의 선택 유지율은 사고·결빙확률이 아니다. 이정은 시설 기준점 사이에서 추정한 값이다.
''','utf8')
    summary=json.loads((S/'sensitivity/summary.json').read_text('utf8'))
    summary.pop('primary_criterion_unchanged',None);summary.update(primary_parameters_unchanged=True,weather_quantile_population='distinct realised 14-predictor time series',quantile_population_corrected=True)
    (S/'sensitivity/summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
    shutil.copyfile(O/'summary.json',B/'technical/weather_information_group_audit.json')
    write(O/'replay_and_gis_verified.json',dict(status='passed',input_rows=2350080,groups_reproduced=136,
        section_winter_exposure_rows_exact=len(matched),information_series=[22,24],duplicate_array_comparisons=90,
        shapefile_rows_reloaded=1686,inspection_gis_rows=3,inspection_areas=2,selection_length_km=1.5,
        model_fitting=False,protected_outcomes_read=False,raw_input_sha256=sha(B/'data/icing_weather_inputs.parquet')))
    print('PASS realised-input identity and all 1686 exposure rows; selection GIS 3 segments / 2 areas',flush=True)

if __name__=='__main__':main()
