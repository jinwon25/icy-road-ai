"""포함된 첫 겨울 입력과 연구 모델을 읽어 새 가중 실험을 접속 없이 재현한다."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.method_blending import domain,ALLOWED
from src.offline_runtime import deny_network
from src.temperature_transfer import regression_report
from src.qa633_metrics import daily_table,aggregate


def read(path):return json.loads(path.read_text('utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--package',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();package=args.package.resolve();out=args.output.resolve()
    if out.exists():raise FileExistsError('Existing reproduction results preserved')
    research=package/'research/freezing_weight'
    source=package/'data/research_weather_inputs.parquet'
    recipe=read(research/'delivery_inputs.json')
    assert sha(source)==recipe['weather_input_sha256']
    data=domain(pd.read_parquet(source));assert set(data.station)==ALLOWED
    groups=read(research/'groups.json');records=read(research/'fit_receipts.json')
    summary=read(research/'summary.json');assert len(records)==20
    replayed=0
    with deny_network() as attempts,threadpool_limits(limits=2):
        for r in records:
            forbidden=set().union(*(set(groups[g]) for g in r['excluded_groups']))
            train=data.loc[~data.station.isin(forbidden)&np.isfinite(data.road_temp)&np.isfinite(data.asos_air_temp)]
            query=data.loc[data.station.isin(forbidden)]
            assert len(train)==r['training_rows'] and sorted(train.station.unique())==r['training_stations']
            digest=hashlib.sha256(pd.util.hash_pandas_object(train[['station','time','road_temp',*r['features']]],index=True).to_numpy().tobytes()).hexdigest()
            assert digest==r['training_values_sha256']
            y=train.road_temp.to_numpy(float);w=1+4*np.exp(-.5*(y/2)**2);w/=w.mean()
            assert hashlib.sha256(w.tobytes()).hexdigest()==r['weights_sha256']
            path=research/r['model_path'];assert sha(path)==r['model_sha256']
            model=joblib.load(path);stored=pd.read_parquet(path.parent/'predictions.parquet')
            pd.testing.assert_frame_equal(stored[['station','time']],query[['station','time']].reset_index(drop=True))
            predicted=np.where(np.isfinite(query.asos_air_temp),model.predict(query[r['features']]),np.nan)
            np.testing.assert_array_equal(predicted,stored[r['candidate']]);replayed+=len(query)
        f=domain(pd.read_parquet(research/'outer_predictions.parquet'))
        reports={}
        for name,scores in summary['scores'].items():
            temp=regression_report(f,f[name])
            for group in ['pooled','station_macro','near_freezing']:
                for metric in ['mae','rmse','bias']:
                    assert abs(temp[group][metric]-scores['temperature'][group][metric])<1e-12
            reports[name]={}
            for n in [144,130,72,1]:
                r,_=aggregate(daily_table(f,f['ice_'+name],sorted(f.station.unique()),n),sorted(f.station.unique()))
                for metric in ['precision','recall','f1']:
                    key=metric+'_available_station_mean'
                    assert abs(r[key]-scores['ice']['daily'][str(n)][key])<1e-12
                reports[name][str(n)]=r
    assert attempts==[]
    out.mkdir(parents=True)
    (out/'reproduction.json').write_text(json.dumps(dict(status='freezing_research_delivery_reproduced',
        model_count=20,prediction_values_verified=replayed,metric_reports_verified=32,
        training_data_station_count=23,network_attempts=0,new_fits=0,assessment_outcomes_used=False,
        reports=reports),ensure_ascii=False,indent=2),encoding='utf-8')
    print('연구 모델20개·예측',replayed,'값·32지표 보고서 재현 완료')


if __name__=='__main__':main()
