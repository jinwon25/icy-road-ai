"""공간 제외 예측을 실제 제출 runtime으로 재실행해 결측까지 동일하게 평가한다."""
import json
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.runtime_metrics import runtime_daily as daily
from src.submission_runtime import infer,FEATURES,WATER
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation

def main():
    out=ROOT/'outputs/private/two_winter_models_20261024_v1'
    target=out/'audit_runtime.json'
    if target.exists():raise FileExistsError('Preserve runtime audit')
    freeze=preservation();audit=json.loads((out/'audit.json').read_text('utf-8'))
    fits=json.loads((out/'fits.json').read_text('utf-8'));frame=pd.read_parquet(out/'audited_predictions.parquet')
    checks=[];physical={};temperature=[]
    with deny_network() as attempts:
        for scope in ['first','both']:
            column='physical_'+scope;frame[column]=np.nan
            for group,part in frame.groupby('group'):
                records=[r for r in fits if r['kind']=='temperature' and r['scope']==scope and r['context']==[group]]
                assert len(records)==2
                models=[joblib.load(out/r['model_path']) for r in records]
                weather=part.loc[:,list(dict.fromkeys(['station','time',*FEATURES,*WATER]))]
                result=infer(weather,models)
                np.testing.assert_allclose(result.estimated_road_temp_c,part['temperature_'+scope],rtol=0,atol=1e-12,equal_nan=True)
                frame.loc[part.index,column]=result.predicted_ice.to_numpy(float,na_value=np.nan)
                checks.append(dict(group=group,scope=scope,rows=len(part),missing_predictions=int(result.predicted_ice.isna().sum())))
            physical[scope]={}
            for period in ['all',2024,2025]:
                f=frame if period=='all' else frame.loc[frame.winter.eq(period)]
                report,_,_=daily(f,f[column]);physical[scope][str(period)]=report
    assert not attempts and preservation()==freeze
    corrected=out/'runtime_predictions.parquet';frame.to_parquet(corrected,index=False,compression='zstd')
    audit.update(physical=physical,physical_runtime_replay=True,runtime_checks=checks,runtime_prediction_sha256=sha(corrected),
        previous_audit_sha256=sha(out/'audit.json'),runtime_sha256=sha(ROOT/'src/submission_runtime.py'),network_attempts=0,
        correction='입력 부족의 물리 판정은 0이 아니라 null. 원 감사는 보존하고 제출 runtime과 동일한 결측으로 정정.')
    target.write_text(json.dumps(audit,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    print(json.dumps(dict(checks=checks,physical=physical),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
