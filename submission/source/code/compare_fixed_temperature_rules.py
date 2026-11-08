"""포함된 지역 제외 예측으로 온도 기준 두 가지의 결빙 지표를 재집계한다."""
from pathlib import Path
import argparse,json,sys
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.evaluation import evaluate,WINTERS

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert not a.output.exists(),'새 출력 폴더를 지정하세요.'
    f=pd.read_parquet(ROOT/'results/evaluation/development_predictions.parquet')
    assert len(set(f.station))==9 and not set(f.station)&{'12410','33411','23402','33402','33406','12213','23411'}
    f=f.loc[np.isfinite(f.physical_both)&f.ice.isin([0,1])].sort_values(['station','time']).reset_index(drop=True)
    p=pd.read_parquet(ROOT/'results/evaluation/fixed_temperature_rule_review/temperature_cross_region.parquet')
    f=f.merge(p,on=['station','time'],how='left',validate='one_to_one')
    assert len(f)==309928 and f.prediction.notna().all()
    f['baseline']=f.physical_both
    wet=(f.aws_dewpoint.ge(f.prediction)&f.aws_age_minutes.between(0,60,inclusive='right'))|f.rain15_max_3h.gt(0)|f.asos_snow_cm.gt(0)
    f['temperature63']=(f.prediction.le(0)&wet).astype(float)
    f['joint_temperature']=(f.baseline.eq(1)&f.temperature63.eq(1)).astype(float)
    rows=[]
    for name in ['baseline','temperature63','joint_temperature']:
        for scope,part,minimum,winters in [('all',f,1,WINTERS),('strict144',f,144,WINTERS),
            *[(str(y),f.loc[f.winter.eq(y)],1,[w for w in WINTERS if w[0].startswith(str(y))]) for y in [2024,2025]],
            *[(group,q,1,WINTERS) for group,q in f.groupby('group')]]:
            r=evaluate(part,part[name],minimum_valid_slots=minimum,winters=winters)[0]
            rows.append(dict(rule=name,scope=scope,**{k:r[k] for k in ['precision','recall','f1','tp','fp','fn']}))
    a.output.mkdir(parents=True)
    table=pd.DataFrame(rows);table.to_csv(a.output/'comparison.csv',index=False)
    expected=pd.read_csv(ROOT/'results/evaluation/fixed_temperature_rule_review/comparison.csv',float_precision='round_trip')
    pd.testing.assert_frame_equal(table,expected,check_exact=True)
    receipt=dict(status='exact_fixed_rule_metrics_reproduced',common_rows=len(f),comparison_rows=len(table),
        model_fits=0,threshold_searches=0,production_model_changed=False,protected_outcomes_used=False)
    (a.output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
