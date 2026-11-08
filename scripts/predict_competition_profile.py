"""보존된 온도 모형을 사용하고 결빙 선택 목적을 명시해 별도 CSV로 추론한다."""
import argparse
import json
from pathlib import Path
import sys
import joblib
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.competition_icing_profiles import PROFILES,apply_icing_profile
from src.extended_runtime import infer
from src.submission_io import read_weather
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,default=ROOT if (ROOT/'extended_training_plan.json').exists() else ROOT/'outputs/private/submission_candidate_20261101_v10')
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--icing-profile',required=True,choices=PROFILES)
    parser.add_argument('--output-start');parser.add_argument('--output-end');args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Preserve previous predictions')
    bundle=args.bundle.resolve();plan=json.loads((bundle/'extended_training_plan.json').read_text(encoding='utf8'))
    receipt=json.loads((bundle/'model/refit_receipt.json').read_text(encoding='utf8'));checks={r['name']:r['sha256'] for r in receipt['models']}
    models={'temperature':[],'icing_reference':[]}
    with deny_network() as attempts:
        for spec in plan['models']:
            path=bundle/'model'/(spec['name']+'.joblib');assert sha(path)==checks[spec['name']]
            models[spec['role']].append(joblib.load(path))
        weather=read_weather(args.input)
        current=infer(weather,models['temperature'],models['icing_reference'],plan['temperature_feature_kind'],plan['temperature_weights'])
        result=apply_icing_profile(weather,current,args.icing_profile)
        for raw in [args.output_start,args.output_end]:
            if raw is not None and pd.Timestamp(raw).tz is not None:raise ValueError('Naive KST output dates required')
        if args.output_start:result=result.loc[result.time.ge(pd.Timestamp(args.output_start))]
        if args.output_end:result=result.loc[result.time.lt(pd.Timestamp(args.output_end))]
        if result.empty:raise ValueError('Empty output period')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        if args.output.suffix=='.parquet':result.to_parquet(args.output,index=False,compression='zstd')
        else:result.to_csv(args.output,index=False,encoding='utf-8-sig')
    assert not attempts
    print(json.dumps(dict(status='explicit_competition_profile_inference_complete',profile=args.icing_profile,rows=len(result),
        missing_ice_rows=int(result.predicted_ice.isna().sum()),road_temperature_model_changed=False,official_score=False,network_attempts=0),ensure_ascii=False))


if __name__=='__main__':main()
