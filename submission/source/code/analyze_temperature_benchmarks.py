"""고정한 회귀와 참조 기준의 같은 관측쌍 성능을 재현한다."""
from pathlib import Path
import sys,argparse,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.evidence_analysis import evaluate,resampling

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():raise FileExistsError('Choose a new output directory')
    a.output.mkdir(parents=True)
    f=pd.read_parquet(ROOT/'results/evaluation/temperature_benchmarks/observations_predictions.parquet')
    methods={'asos_air_reference':'asos_air_temperature','aws_air_reference':'aws_air_temperature','asos_ground_reference':'asos_ground_temp',
        'weather12_regression':'reference_temperature_12','estimated':'estimated_road_temperature_c'}
    rows=[];target='observed_road_temperature_c'
    for scope,q in [('all_temperature',f),('near_freezing_observed_pm2c',f.loc[f[target].between(-2,2)])]:
        rows.extend([dict(temperature_scope=scope,**r) for r in evaluate(q,target,methods)])
    pd.DataFrame(rows).to_csv(a.output/'metrics.csv',index=False,encoding='utf-8-sig')
    uncertainty=resampling(f,target,methods,np.random.default_rng(61107))
    pd.DataFrame(uncertainty).to_csv(a.output/'paired_day_block_sensitivity.csv',index=False,encoding='utf-8-sig')
    print(json.dumps(dict(rows=len(f),metrics=len(rows),resamples=2000,training=False),ensure_ascii=False))
if __name__=='__main__':main()
