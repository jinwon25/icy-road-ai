"""포함 구간 자료에서 계측 검토 대상을 다시 계산한다."""
from pathlib import Path
import sys,argparse,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.section_review import select_inspection_segments
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'results/sections/section_review.csv');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise FileExistsError('Choose a new output file')
 f=pd.read_csv(a.input,float_precision='round_trip');result,thresholds=select_inspection_segments(f)
 a.output.parent.mkdir(parents=True,exist_ok=True);result.to_csv(a.output,index=False,encoding='utf-8-sig')
 print(json.dumps(dict(segments=result.seg_id.nunique(),**thresholds),ensure_ascii=False))
if __name__=='__main__':main()
