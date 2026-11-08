"""지역·겨울 검증을 통과한 풍속 보완 모형을 순수 과거 기상 입력으로 실행한다."""
import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.wind_network_runtime import predict_wind_network
from src.offline_runtime import deny_network


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,default=Path('.'));p.add_argument('--input',required=True,type=Path)
    p.add_argument('--aws-input',required=True,type=Path);p.add_argument('--points',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();bundle=args.bundle.resolve()
    if args.output.exists():raise FileExistsError('Use a new prediction output')
    read=lambda path:pd.read_parquet(path) if path.suffix=='.parquet' else pd.read_csv(path,dtype={'station':str},float_precision='round_trip')
    with deny_network() as attempts:
        result=predict_wind_network(read(args.input),read(args.points),read(args.aws_input),
            read(bundle/'data/aws_coordinates.csv'),bundle/'model')
    assert not attempts
    args.output.parent.mkdir(parents=True,exist_ok=True);result.to_csv(args.output,index=False,encoding='utf-8-sig')
    print('Wind predictions',len(result),'available',int(result.estimated_wind_speed_ms_available.sum()),flush=True)


if __name__=='__main__':main()
