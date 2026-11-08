"""겨울별 기상·도로환경 기준과 공식 목록을 같은 500m 키로 연결한다."""
from pathlib import Path
import sys
import pandas as pd,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
P=ROOT/'outputs/private';B=P/'competition_submission/icy_road_model';W=P/'editorial_review_20261106'
def main():
 plan=W/'inspection_criteria.json'
 settings=dict(both_winters_review_code=4,minimum_availability=.95,inventory_relation='outside_inventory_for_margin',margin_m=250,
 requires_estimated_chainage=True,contiguous_maximum_gap_km=.12,
 interpretation='현장 계측·시설 확인 우선 범위. 결빙 발생·사고·공식 지정의 검증 또는 자동 조치 대상이 아님',
 independent_ice_outcomes_used=False)
 if not plan.exists():write(plan,settings)
 else:assert read(plan)==settings
 f=pd.read_csv(B/'results/sections/section_review.csv',float_precision='round_trip')
 inv=pd.read_csv(P/'vulnerability_map_comparison_20261031_v1/segment_screening.csv',float_precision='round_trip')
 keys=['seg_id','chain_id','current_relation','current_nominal_overlap']
 f=f.merge(inv[keys],on='seg_id',validate='many_to_one');assert len(f)==1686
 a=f.groupby('seg_id').agg(winters=('winter','nunique'),minimum_review_code=('review_code','min'),minimum_availability=('condition_availability','min'))
 selected=a.index[(a.winters==2)&(a.minimum_review_code==4)&(a.minimum_availability>=.95)]
 q=f.loc[f.winter.eq(2024)&f.seg_id.isin(selected)&f.current_relation.eq('outside_inventory_for_margin')&f.chainage_available].copy()
 q=q.sort_values(['route_nm','chain_id','estimated_km_lo']);corridors=[];groups=[]
 for _,part in q.groupby('chain_id',sort=True):
  cluster=[];end=None
  for index,row in part.iterrows():
   if end is not None and row.estimated_km_lo>end+.12:
    groups.append(cluster);cluster=[]
   cluster.append(index);end=row.estimated_km_hi if end is None else max(end,row.estimated_km_hi)
  if cluster:groups.append(cluster)
 for i,indices in enumerate(groups,1):
  part=q.loc[indices];ids=set(part.seg_id);both=f.loc[f.seg_id.isin(ids)]
  r=dict(area_id=f'F{i:02d}',route=part.route_nm.iloc[0],direction=part.flow_lbl.iloc[0],
   estimated_km_start=float(part.estimated_km_lo.min()),estimated_km_end=float(part.estimated_km_hi.max()),segments=len(part),
   directional_length_km=float(part.len_m.sum()/1000),bridge_segments=int(part.bridge_code_fraction.gt(0).sum()),
   curve_context_segments=int(part.curve_deg_100m.gt(f.drop_duplicates('seg_id').curve_deg_100m.quantile(.75)).sum()),
   exposure_pct_2024=float(np.average(both.loc[both.winter.eq(2024),'weather_index_100'],weights=both.loc[both.winter.eq(2024),'len_m'])),
   exposure_pct_2025=float(np.average(both.loc[both.winter.eq(2025),'weather_index_100'],weights=both.loc[both.winter.eq(2025),'len_m'])),
   official_location_verified=False)
  corridors.append(r);f.loc[f.seg_id.isin(ids),'inspection_area_id']=r['area_id']
 f['inspection_candidate']=f.seg_id.isin(set(q.seg_id));f.to_csv(B/'results/sections/section_review.csv',index=False,encoding='utf-8-sig')
 q.to_csv(B/'results/sections/inspection_segments.csv',index=False,encoding='utf-8-sig')
 pd.DataFrame(corridors).to_csv(B/'results/sections/inspection_areas.csv',index=False,encoding='utf-8-sig')
 write(W/'inspection_review.json',dict(settings=settings,segments=len(q),directional_km=float(q.len_m.sum()/1000),areas=corridors,
 criteria_sha256=sha(plan),source_inventory_sha256=sha(P/'vulnerability_map_comparison_20261031_v1/segment_screening.csv')))
 print('INSPECTION',len(q),'segments,',len(corridors),'continuous directional areas',flush=True)
 print(pd.DataFrame(corridors).to_string(index=False),flush=True)
if __name__=='__main__':main()
