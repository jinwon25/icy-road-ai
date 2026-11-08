"""도로 기상 보완 모형의 CSV 추론. 기존 결빙·노면온도 실행과 분리한다."""
import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.offline_runtime import deny_network
from src.road_weather_runtime import predict_weather


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Preserve existing prediction CSV')
    frame=pd.read_csv(args.input,dtype={'station':str})
    with deny_network() as attempts:result=predict_weather(frame,args.model)
    assert not attempts
    result.to_csv(args.output,index=False,encoding='utf-8-sig')
    print('기상 추정 완료:',len(result),'행',flush=True)


if __name__=='__main__':main()
