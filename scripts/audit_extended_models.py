"""완료된 확장 후보의 저장 모델·지역 제외·예측·회귀 수치를 재검산한다."""
import argparse
import json
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.thermal_refinement import feature_table
from src.two_winter import validate
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation
from src.offline_runtime import deny_network


def read(path):return json.loads(path.read_text('utf-8'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--search',type=Path,required=True)
    p.add_argument('--candidate',action='append',required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output
    if out.exists():raise FileExistsError('Preserve model audit')
    frozen=preservation();plan=read(args.search/'plan.json');settings=plan['settings']
    source=ROOT/settings['data'];assert sha(source)==plan['signatures']['data']
    data=validate(pd.read_parquet(source)).sort_values(['station','time']).reset_index(drop=True)
    specs={s['name']:s for s in settings['candidates']};checks=[];features={}
    with deny_network() as attempts,threadpool_limits(limits=2):
        for name in args.candidate:
            spec=specs[name];folder=args.search/name;report=read(folder/'report.json')
            kind=spec.get('features','weather')
            if kind not in features:features[kind]=feature_table(data,kind)
            x=features[kind];parts=[];rows=0
            for fit in report['fits']:
                group=fit['group'];modelpath=folder/(group+'.joblib');predpath=folder/(group+'.parquet')
                assert sha(modelpath)==fit['model_sha256'] and sha(predpath)==fit['prediction_sha256']
                query=data.loc[data.group.eq(group)]
                train=data.loc[~data.group.eq(group)&data.road_temp.notna()&data.asos_air_temp.notna()]
                assert len(train)==fit['training_rows'] and sorted(train.station.unique())==fit['training_stations']
                assert not set(train.station)&set(query.station)
                model=joblib.load(modelpath);expected=pd.read_parquet(predpath)
                pd.testing.assert_frame_equal(query[['station','time']].reset_index(drop=True),expected[['station','time']].reset_index(drop=True))
                assert list(x)==fit['features']
                actual=model.predict(x.loc[query.index])
                if spec.get('residual'):actual=actual+query.asos_air_temp.to_numpy()
                actual=np.where(query.asos_air_temp.notna(),actual,np.nan)
                np.testing.assert_allclose(actual,expected.prediction,rtol=0,atol=1e-10,equal_nan=True)
                parts.append(expected);rows+=len(expected)
            f=pd.concat(parts).sort_values(['station','time']).reset_index(drop=True)
            stored=pd.read_parquet(folder/'predictions.parquet')
            pd.testing.assert_frame_equal(f,stored,check_exact=True)
            valid=f.road_temp.notna()&f.prediction.notna();error=f.loc[valid,'prediction'].to_numpy()-f.loc[valid,'road_temp'].to_numpy()
            mae=float(np.abs(error).sum()/len(error));rmse=float(np.sqrt((error**2).sum()/len(error)))
            assert abs(mae-report['regression']['pooled']['mae'])<1e-12
            assert abs(rmse-report['regression']['pooled']['rmse'])<1e-12
            checks.append(dict(candidate=name,models=len(parts),prediction_rows=rows,mae=mae,rmse=rmse,
                predictions_sha256=sha(folder/'predictions.parquet'),report_sha256=sha(folder/'report.json')))
    assert preservation()==frozen and not attempts
    out.mkdir(parents=True)
    result=dict(status='saved_models_replayed_and_verified',checks=checks,protected_labels_read=False,
        old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],network_attempts=0,
        plan_sha256=sha(args.search/'plan.json'),audit_code_sha256=sha(Path(__file__)))
    (out/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
