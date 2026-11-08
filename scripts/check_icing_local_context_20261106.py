"""학습 정답을 읽지 않고 허용 도로기상 지점의 제공 도로환경 가용 범위를 확인."""
from pathlib import Path
import json
import pandas as pd,geopandas as gpd
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'outputs/private';out=P/'icing_local_context_feasibility_20261106'
assert not out.exists()
points=pd.read_csv(P/'weather_network_review_20261010_v1/metadata_analysis/development_points.csv',dtype={'station':str})
assert len(points)==23 and not set(points.station)&{'12410','33411','23402','33402','33406','12213','23411'}
lines=gpd.read_file(P/'competition_submission/icy_road_model/results/sections/risk_review.gpkg',layer='winter_2024')
needed=['seg_id','bridge_code_fraction','tunnel_code_fraction','curve_deg_100m','geometry']
lines=lines[needed].to_crs('EPSG:5186')
gp=gpd.GeoDataFrame(points,geometry=gpd.points_from_xy(points.lon,points.lat),crs='EPSG:4326').to_crs(lines.crs)
joined=gpd.sjoin_nearest(gp,lines,how='left',distance_col='nearest_section_distance_m')
joined=joined.sort_values(['station','nearest_section_distance_m','seg_id']).drop_duplicates('station')
joined['context_within_250m']=joined.nearest_section_distance_m.le(250)
joined=joined.drop(columns=['geometry','index_right'])
out.mkdir();joined.to_csv(out/'station_context.csv',index=False,encoding='utf-8-sig')
summary=dict(status='context_feasibility_only',stations=len(joined),within_250m=int(joined.context_within_250m.sum()),
             outside_250m=joined.loc[~joined.context_within_250m,'station'].tolist(),
             model_fitted=False,observed_ice_read=False,description='500m 분석구간의 도로시설 비율. 실제 센서 설치지점의 교량 여부로 확정하지 않음.')
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
print(joined.to_string(index=False),flush=True)
