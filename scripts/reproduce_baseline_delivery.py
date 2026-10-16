"""제출 묶음 내부의 고정 예측으로 단순 기준선 24개 보고서를 재현한다."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.qa633_metrics import daily_table, aggregate
from src.offline_runtime import deny_network


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--package-root',type=Path,default=ROOT)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Existing baseline replay is preserved')
    base=args.package_root/'research/baselines'
    expected=json.loads((base/'summary.json').read_text('utf-8'))
    with deny_network() as attempts:
        frame=pd.read_parquet(base/'fixed_comparator_predictions.parquet')
        pop=expected['population'];reports={}
        for method,item in expected['reports'].items():
            values={}
            for minimum in [144,130,72,1]:
                days=daily_table(frame,frame[method],pop,minimum)
                result,_=aggregate(days,pop)
                for key,value in result.items():
                    previous=item['coverage'][str(minimum)][key]
                    if isinstance(value,float):
                        assert np.isclose(value,previous,atol=1e-12,rtol=0),(method,minimum,key)
                    else: assert value==previous,(method,minimum,key)
                values[str(minimum)]=result
            reports[method]=values
    assert attempts==[]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'status':'baseline_delivery_replayed','reports':reports,
        'verified_reports':len(reports)*4,'network_attempts':len(attempts),'new_model_fits':0},ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    print('24 fixed baseline reports reproduced; network attempts=0')


if __name__=='__main__':main()
