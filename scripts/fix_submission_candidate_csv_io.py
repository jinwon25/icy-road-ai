"""실패한 최초CLI결과를 보존하고 입력CSV의 무손실 파서로 별도 재현검사를 구성."""
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import write,read
from src.data_source import sha256_file as sha

OUT=ROOT/'outputs/private/submission_candidate_20261013_v1'

RUNNER='''"""CSV round_trip 입력을 사용하는 대표 후보의 로컬 추론."""
from pathlib import Path
import argparse,json
import joblib
from runtime import FEATURES,infer
from submission_io import read_weather
from offline_runtime import deny_network
HERE=Path(__file__).resolve().parent.parent
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--input',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--models',type=Path,default=HERE/'model');args=parser.parse_args()
 if args.output.exists():raise FileExistsError('Existing prediction preserved')
 with deny_network() as attempts:
  data=read_weather(args.input);models=[joblib.load(args.models/(n+'.joblib')) for n in ['weather12_mse300','weather12_mae300']];result=infer(data,models)
  args.output.parent.mkdir(parents=True,exist_ok=True)
  if args.output.suffix.lower()=='.parquet':result.to_parquet(args.output,index=False)
  else:result.to_csv(args.output,index=False,encoding='utf-8-sig',na_rep='')
 assert attempts==[]
 print(json.dumps({'status':'candidate_lossless_csv_inference_complete','rows':len(result),'temperature_available':int(result.estimated_road_temp_c.notna().sum()),'ice_available':int(result.predicted_ice.notna().sum()),'network_attempts':len(attempts),'official_csv_schema':False,'operational_warning':False}))
if __name__=='__main__':main()
'''


def main():
    target=OUT/'validation/csv_io_fix_receipt.json'
    if target.exists():raise FileExistsError('Preserve CSV fix')
    old=OUT/'code/predict.py';shutil.copy2(old,OUT/'validation/predict_parser_v1.py')
    shutil.copy2(ROOT/'src/submission_runtime.py',OUT/'code/runtime.py')
    shutil.copy2(ROOT/'src/submission_io.py',OUT/'code/submission_io.py')
    old.write_text(RUNNER,encoding='utf-8')
    write(target,dict(status='lossless_csv_io_prepared',issue='처음 기본 CSV 파서의 반올림이144행 중5행의 온도 예측을 바꿈',
        failed_outputs_preserved=['validation/cli_example.csv','validation/cli_targets','validation/cli_segment','validation/predict_parser_v1.py'],
        solution='pandas.read_csv float_precision=round_trip',trained_models_changed=False,spatial_predictions_changed=False,
        previous_independent_audit_preserved=True,reader_source_sha256=sha(ROOT/'src/submission_io.py'),runner_sha256=sha(old)))


if __name__=='__main__':main()
