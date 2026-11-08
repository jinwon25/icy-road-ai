"""75개 사전 명시 기준에서 현장 검토 구간이 유지되는지 계산한다. 결빙 정답 불사용."""
from pathlib import Path
from itertools import product
from datetime import datetime,timezone
import sys,json,shutil
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.inspection_sensitivity import inspection_scenario
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/judging_upgrade_20261106';B=W/'icy_road_model';O=W/'information_sensitivity'

def write(p,x):
    with p.open('x',encoding='utf8') as out:json.dump(x,out,ensure_ascii=False,indent=2,allow_nan=False);out.write('\n')

def main():
    O.mkdir()
    paths=[B/'results/sections/section_review.csv',B/'results/inventory/overlap_sensitivity.csv',ROOT/'src/inspection_sensitivity.py',Path(__file__)]
    write(O/'plan.json',dict(created_utc=datetime.now(timezone.utc).isoformat(),
        weather_quantiles=[.6,.7,.75,.8,.9],curve_quantiles=[.6,.7,.75,.8,.9],inventory_margins_m=[100,250,500],
        primary={'weather_quantile':.75,'curve_quantile':.75,'margin_m':250,'minimum_availability':.95},
        availability_sensitivity=[.9,.95,.99],both_winters_required=True,protected_outcomes_read=False,
        interpretation='선택 유지율은 선언한 75개 자체 기준 중 충족 비율. 결빙확률·사고확률·통계적 신뢰도가 아님',
        no_reselection_of_primary_criterion=True,signatures={p.relative_to(ROOT).as_posix():sha(p) for p in paths}))
    f=pd.read_csv(paths[0],dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
    overlap=pd.read_csv(paths[1],dtype={'seg_id':str},float_precision='round_trip')
    base,settings=inspection_scenario(f,overlap)
    selected=set(base.index[base.selected]);expected=set(f.loc[f.inspection_candidate,'seg_id'])
    assert selected==expected and len(selected)==3
    rows=[];selection=[];all_ids=sorted(base.index)
    for number,(w,c,m) in enumerate(product([.6,.7,.75,.8,.9],[.6,.7,.75,.8,.9],[100,250,500]),1):
        census,s=inspection_scenario(f,overlap,w,c,m)
        ids=set(census.index[census.selected]);intersection=ids&selected;union=ids|selected
        rows.append(dict(scenario=number,weather_quantile=w,curve_quantile=c,margin_m=m,selected_segments=len(ids),
            retained_primary_segments=len(intersection),additional_segments=len(ids-selected),
            jaccard_with_primary=len(intersection)/len(union) if union else 1.,
            **{f'weather_threshold_{y}':v for y,v in s['weather_threshold_by_winter'].items()},curve_threshold=s['curve_threshold_deg_100m']))
        selection.append([sid in ids for sid in all_ids])
    matrix=np.array(selection,dtype=bool)
    census=f.drop_duplicates('seg_id').set_index('seg_id').loc[all_ids].copy()
    keep=['route_nm','flow_lbl','estimated_km_lo','estimated_km_hi','inspection_area_id','inspection_candidate',
        'bridge_code_fraction','curve_deg_100m','chainage_available']
    census=census[keep];census['selected_scenarios']=matrix.sum(axis=0);census['declared_scenarios']=len(rows)
    census['selection_fraction']=matrix.mean(axis=0);census['selected_in_all_scenarios']=matrix.all(axis=0)
    census.reset_index().to_csv(O/'segment_stability.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(rows).to_csv(O/'scenario_summary.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(matrix.T,index=all_ids,columns=[f'scenario_{i:02d}' for i in range(1,76)]).rename_axis('seg_id').to_csv(O/'scenario_membership.csv',encoding='utf-8-sig')
    focus=census.loc[census.inspection_candidate].reset_index()
    area=focus.groupby('inspection_area_id').agg(segments=('seg_id','size'),minimum_selection_fraction=('selection_fraction','min'),
        maximum_selection_fraction=('selection_fraction','max'),persistent_segments=('selected_in_all_scenarios','sum')).reset_index()
    area.to_csv(O/'area_stability.csv',index=False,encoding='utf-8-sig')
    waterfall=[];mask=pd.Series(True,index=base.index)
    for name in ['criterion_available','criterion_weather','criterion_environment','criterion_alignment','criterion_outside_inventory']:
        before=int(mask.sum());mask &=base[name]
        waterfall.append(dict(criterion=name,before=before,after=int(mask.sum()),removed=before-int(mask.sum())))
    pd.DataFrame(waterfall).to_csv(O/'criterion_intersections.csv',index=False,encoding='utf-8-sig')
    availability=[]
    for minimum in [.9,.95,.99]:
        r,_=inspection_scenario(f,overlap,minimum_availability=minimum)
        availability.append(dict(minimum_availability=minimum,selected_segments=int(r.selected.sum())))
    pd.DataFrame(availability).to_csv(O/'availability_sensitivity.csv',index=False,encoding='utf-8-sig')
    summary=dict(status='inspection_sensitivity_computed',scenarios=len(rows),primary_segments=len(selected),
        minimum_selected_segments=min(r['selected_segments'] for r in rows),maximum_selected_segments=max(r['selected_segments'] for r in rows),
        persistent_primary_segments=int(focus.selected_in_all_scenarios.sum()),persistent_all_segments=int(census.selected_in_all_scenarios.sum()),
        primary_selection_min_fraction=float(focus.selection_fraction.min()),weather_groups_by_winter={str(y):int(q.weather_information_group.nunique()) for y,q in f.groupby('winter')},
        source_census=len(census),criteria=settings,waterfall=waterfall,availability=availability,areas=area.to_dict('records'),
        primary_criterion_unchanged=True,ice_outcomes_used=False)
    write(O/'summary.json',summary)
    target=B/'results/sections/sensitivity';previous=W/'sensitivity_before_information_fix'
    assert target.resolve().is_relative_to(W.resolve()) and previous.resolve().is_relative_to(W.resolve()) and not previous.exists()
    target.rename(previous);shutil.copytree(O,target)
    shutil.copyfile(ROOT/'src/inspection_sensitivity.py',B/'src/inspection_sensitivity.py')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
