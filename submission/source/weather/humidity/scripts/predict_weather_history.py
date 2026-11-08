"""과거 입력을 포함해 추론한 뒤 원하는 기간만 출력한다. 먼저 잘라서 이력을 잃지 않는다."""
import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.offline_runtime import deny_network
from src.weather_history_runtime import predict_weather_history


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--base-model',type=Path,default=ROOT/'model/weather_v1')
    parser.add_argument('--history-model',type=Path,default=ROOT/'model/humidity_history_v1')
    parser.add_argument('--output-start');parser.add_argument('--output-end')
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Existing weather prediction is preserved')
    frame=pd.read_parquet(args.input) if args.input.suffix=='.parquet' else pd.read_csv(args.input,dtype={'station':str},float_precision='round_trip')
    with deny_network() as attempts:result=predict_weather_history(frame,args.base_model,args.history_model)
    if attempts:raise RuntimeError('Unexpected weather inference network attempt')
    if args.output_start:result=result.loc[result.time.ge(pd.Timestamp(args.output_start))]
    if args.output_end:result=result.loc[result.time.lt(pd.Timestamp(args.output_end))]
    if result.empty:raise ValueError('Output interval contains no weather rows')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.suffix=='.parquet':result.to_parquet(args.output,index=False)
    else:result.to_csv(args.output,index=False,encoding='utf-8-sig')
    print('WEATHER HISTORY PREDICTION',len(result),'rows',flush=True)


if __name__=='__main__':main()
