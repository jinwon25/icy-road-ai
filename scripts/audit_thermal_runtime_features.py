"""학습용 지점 제한에 의존하지 않는 배포 특징을 허용 23곳에서 검산한다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.thermal_runtime import thermal_predictors,EXTRA
from src.thermal_extended import feature_table
from src.submission_runtime import FEATURES
from src.two_winter import validate
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation
from src.offline_runtime import deny_network


def main():
    private=ROOT/'outputs/private';out=private/'thermal_runtime_feature_audit_20261024_v1'
    if out.exists():raise FileExistsError('Preserve feature audit')
    freeze=preservation();source=private/'canonical_thermal_data_20261024_v1/development.parquet'
    assert sha(source)==json.loads((source.parent/'receipt.json').read_text('utf-8'))['data_sha256']
    columns=list(dict.fromkeys(['station','time','winter',*FEATURES,*EXTRA]))
    data=validate(pd.read_parquet(source,columns=columns));raw=data.drop(columns='winter');checks=[]
    with deny_network() as attempts:
        for kind in ['thermal','thermal_history']:
            expected=feature_table(data,kind);actual,valid,stale=thermal_predictors(raw,kind)
            pd.testing.assert_frame_equal(actual,expected,check_exact=True)
            checks.append(dict(kind=kind,rows=len(data),features=len(actual.columns),values=int(actual.size),
                valid_temperature_rows=int(valid.sum()),missing_or_stale_aws_rows=int(stale.sum())))
    assert not attempts and preservation()==freeze
    out.mkdir();result=dict(status='research_and_deployment_features_match_exactly',checks=checks,
        protected_labels_read=False,any_outcome_columns_read=False,network_attempts=0,data_sha256=sha(source),
        signatures={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'src/thermal_runtime.py',ROOT/'src/thermal_extended.py',ROOT/'src/extended_search.py']})
    (out/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
