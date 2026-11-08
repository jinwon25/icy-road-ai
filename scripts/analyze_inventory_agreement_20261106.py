"""공개 목록과 고정 기상 기준의 일치 범위를 기술한다. 미포함 구간을 음성으로 쓰지 않는다."""
from pathlib import Path
import sys,json
import pandas as pd,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model'

def main():
    out=B/'results/inventory/agreement';assert not out.exists();out.mkdir()
    paths=[B/'results/sections/section_review.csv',B/'results/inventory/overlap_sensitivity.csv',B/'results/inventory/inventory_mapping.csv']
    f=pd.read_csv(paths[0],dtype={'seg_id':str},float_precision='round_trip')
    overlap=pd.read_csv(paths[1],dtype={'seg_id':str},float_precision='round_trip')
    mapping=pd.read_csv(paths[2]);first=f.loc[f.winter.eq(2024)].set_index('seg_id')
    winter=f.pivot(index='seg_id',columns='winter',values='weather_index_100')
    thresholds=f.groupby('winter').weather_upper_threshold.first()
    base=first.copy();base['weather_both']=winter.ge(thresholds,axis=1).all(axis=1)
    rows=[];records=[]
    for source in sorted(overlap.version.unique()):
        nominal=overlap.loc[overlap.version.eq(source)&overlap.margin_m.eq(250)&overlap.nominal_overlap_km.gt(0)]
        ids=set(nominal.seg_id);assert ids<=set(first.index)
        listed=base.loc[sorted(ids)]
        for margin in [100,250,500]:
            o=overlap.loc[overlap.version.eq(source)&overlap.margin_m.eq(margin)]
            possible=set(o.loc[o.possible_overlap_km.gt(0),'seg_id'])
            for q in [.6,.7,.75,.8,.9]:
                t={}
                for year,part in f.groupby('winter'):
                    distinct=part.groupby('weather_information_group').weather_index_100.agg(['min','max'])
                    assert np.allclose(distinct['min'],distinct['max'],rtol=0,atol=1e-12)
                    t[year]=float(distinct['min'].quantile(q))
                w=wind=winter.ge(pd.Series(t),axis=1)
                both=w.all(axis=1)
                cohort=listed.index
                rows.append(dict(source=source,margin_m=margin,weather_quantile=q,
                    nominal_overlap_segments=len(ids),possible_overlap_segments=len(possible),
                    nominal_records_mapped=int(nominal.inventory_id.nunique()),
                    nominal_high_2024=int(w.loc[cohort,2024].sum()),nominal_high_2025=int(w.loc[cohort,2025].sum()),
                    nominal_high_both=int(both.loc[cohort].sum()),
                    nominal_environment=int(listed.environment_context.sum()),
                    nominal_weather_and_environment=int((both&base.environment_context).loc[cohort].sum()),
                    high_both_all_segments=int(both.sum()),threshold_2024=t[2024],threshold_2025=t[2025]))
        for ident,part in nominal.groupby('inventory_id'):
            piece=base.loc[sorted(set(part.seg_id))]
            records.append(dict(source=source,inventory_id=ident,mapped_segments=len(piece),
                weather_both_segments=int(piece.weather_both.sum()),environment_segments=int(piece.environment_context.sum()),
                route=piece.route_nm.iloc[0],official_location_verified=False))
    table=pd.DataFrame(rows);table.to_csv(out/'threshold_comparison.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(records).to_csv(out/'mapped_inventory_records.csv',index=False,encoding='utf-8-sig')
    current=table.loc[table.source.eq('2026-09-07')&table.margin_m.eq(250)&table.weather_quantile.eq(.75)].iloc[0]
    assert current.nominal_overlap_segments==64 and current.nominal_high_both==0 and current.possible_overlap_segments==81
    assert base.weather_both.sum()==60 and (base.weather_both&base.environment_context).sum()==3
    summary=dict(status='descriptive_inventory_agreement_complete',sources={p.relative_to(B).as_posix():sha(p) for p in paths},
        reference=dict(source_date='2026-09-07',nominal_overlap_segments=64,nominal_inventory_records=8,
            possible_overlap_segments_250m=81,nominal_high_first_winter=int(current.nominal_high_2024),
            nominal_high_second_winter=int(current.nominal_high_2025),nominal_high_both_winters=0),
        all_segments=843,chainage_available=int(first.chainage_available.sum()),chainage_unavailable=int((~first.chainage_available).sum()),
        high_both_segments=60,additional_measurement_segments=3,additional_measurement_areas=2,
        interpretation='두 겨울의 기상 상위 조건은 기존 목록을 재현하는 기준이 아니다. 목록 대조와 추가 계측 탐색을 구분하며 기존 목록을 모형으로 해제하거나 위험을 하향 판정하지 않는다.',
        inventories_are_observed_ice_labels=False,unlisted_segments_are_true_negatives=False,
        inferred_chainage_is_official_survey=False,causal_or_independent_performance_claim=False,
        model_weights_or_thresholds_changed=False,protected_outcomes_used=False)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
    print(table.loc[table.margin_m.eq(250),['source','weather_quantile','nominal_overlap_segments','nominal_high_2024','nominal_high_2025','nominal_high_both']].to_string(index=False),flush=True)
if __name__=='__main__':main()
