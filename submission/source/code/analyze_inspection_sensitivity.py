"""선정 기준 75조합의 결과와 구간별 선택 유지율을 재현한다."""
from pathlib import Path
from itertools import product
import sys,argparse,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.inspection_sensitivity import inspection_scenario

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():raise FileExistsError('Choose a new output directory')
    f=pd.read_csv(ROOT/'results/sections/section_review.csv',dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
    overlap=pd.read_csv(ROOT/'results/inventory/overlap_sensitivity.csv',dtype={'seg_id':str},float_precision='round_trip')
    base,_=inspection_scenario(f,overlap);selected=set(base.index[base.selected]);all_ids=sorted(base.index)
    rows=[];membership=[]
    for n,(w,c,m) in enumerate(product([.6,.7,.75,.8,.9],[.6,.7,.75,.8,.9],[100,250,500]),1):
        census,s=inspection_scenario(f,overlap,w,c,m);ids=set(census.index[census.selected]);intersection=ids&selected;union=ids|selected
        rows.append(dict(scenario=n,weather_quantile=w,curve_quantile=c,margin_m=m,selected_segments=len(ids),
            retained_primary_segments=len(intersection),additional_segments=len(ids-selected),
            jaccard_with_primary=len(intersection)/len(union) if union else 1.,
            **{f'weather_threshold_{y}':v for y,v in s['weather_threshold_by_winter'].items()},curve_threshold=s['curve_threshold_deg_100m']))
        membership.append([sid in ids for sid in all_ids])
    matrix=np.array(membership,dtype=bool);a.output.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(a.output/'scenario_summary.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(matrix.T,index=all_ids,columns=[f'scenario_{i:02d}' for i in range(1,76)]).rename_axis('seg_id').to_csv(a.output/'scenario_membership.csv',encoding='utf-8-sig')
    pd.DataFrame(dict(seg_id=all_ids,selected_scenarios=matrix.sum(axis=0),declared_scenarios=75,selection_fraction=matrix.mean(axis=0))).to_csv(a.output/'segment_stability.csv',index=False,encoding='utf-8-sig')
    print(json.dumps(dict(scenarios=len(rows),primary_segments=len(selected),ice_outcomes_used=False),ensure_ascii=False))
if __name__=='__main__':main()
