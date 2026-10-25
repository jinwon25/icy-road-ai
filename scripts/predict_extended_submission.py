"""포함 모델의 실제 추론. 과거 특징을 먼저 만든 뒤 요청 출력 기간을 선택한다."""
import argparse
import json
from pathlib import Path
import sys
import joblib
import pandas as pd


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output-start');p.add_argument('--output-end');a=p.parse_args()
    base=a.bundle.resolve();sys.path.insert(0,str(base))
    from src.extended_runtime import infer
    from src.submission_io import read_weather
    from src.data_source import sha256_file as sha
    from src.offline_runtime import deny_network
    if a.output.exists():raise FileExistsError('Existing prediction preserved')
    plan=json.loads((base/'extended_training_plan.json').read_text('utf-8'));receipts=json.loads((base/'model/refit_receipt.json').read_text('utf-8'))
    checks={r['name']:r['sha256'] for r in receipts['models']};models={'temperature':[],'icing_reference':[]}
    with deny_network() as attempts:
        for spec in plan['models']:
            path=base/'model'/(spec['name']+'.joblib')
            if sha(path)!=checks[spec['name']]:raise ValueError('Model hash mismatch')
            models[spec['role']].append(joblib.load(path))
        result=infer(read_weather(a.input),models['temperature'],models['icing_reference'],plan['temperature_feature_kind'],plan['temperature_weights'])
        for raw in [a.output_start,a.output_end]:
            if raw is not None and pd.Timestamp(raw).tz is not None:raise ValueError('Output period must be naive KST')
        if a.output_start:result=result.loc[result.time.ge(pd.Timestamp(a.output_start))]
        if a.output_end:result=result.loc[result.time.lt(pd.Timestamp(a.output_end))]
        if result.empty:raise ValueError('Empty requested output period')
        a.output.parent.mkdir(parents=True,exist_ok=True)
        if a.output.suffix.lower()=='.parquet':result.to_parquet(a.output,index=False,compression='zstd')
        else:result.to_csv(a.output,index=False,encoding='utf-8-sig')
    assert not attempts
    print(json.dumps(dict(status='extended_offline_inference_complete',rows=len(result),temperature_available=int(result.estimated_road_temp_c.notna().sum()),
        ice_available=int(result.predicted_ice.notna().sum()),temperature_feature_kind=plan['temperature_feature_kind'],network_attempts=0,official_csv_schema=False),ensure_ascii=False))


if __name__=='__main__':main()
