"""포함된 고정 지역 제외 예측으로 짧은 감쇠 이력 후보의 지표를 재집계한다."""
from pathlib import Path
import argparse,sys,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.evaluation import evaluate,WINTERS
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert not a.output.exists(),'새 출력 폴더를 지정하세요.'
    source=ROOT/'results/evaluation/aws_short_forcing_review';f=pd.read_parquet(source/'predictions.parquet')
    assert len(set(f.station))==9 and not set(f.station)&{'12410','33411','23402','33402','33406','12213','23411'}
    rows=[]
    for name in ['physical','asos_zero','candidate']:
        for scope,q,minimum,winters in [('all',f,1,WINTERS),('strict144',f,144,WINTERS),
            *[(str(y),f.loc[f.winter.eq(y)],1,[w for w in WINTERS if w[0].startswith(str(y))]) for y in [2024,2025]],
            *[(group,q,1,WINTERS) for group,q in f.groupby('group')]]:
            report=evaluate(q,q[name],minimum_valid_slots=minimum,winters=winters)[0]
            rows.append(dict(method=name,scope=scope,**{k:report[k] for k in ['precision','recall','f1','tp','fp','fn']}))
    table=pd.DataFrame(rows);expected=pd.read_csv(source/'comparison.csv',float_precision='round_trip')
    pd.testing.assert_frame_equal(table,expected,check_exact=True)
    a.output.mkdir(parents=True);table.to_csv(a.output/'comparison.csv',index=False)
    result=dict(status='short_forcing_metric_rows_exact',comparison_rows=len(table),model_fits=0,threshold_searches=0,protected_outcomes_used=False)
    (a.output/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
