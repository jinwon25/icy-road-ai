"""포함된 기상 입력과 고정 모형으로 노면온도 비교 표의 참조 예측을 다시 만든다."""
from pathlib import Path
import sys,argparse,json
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.submission_runtime import FEATURES
from src.evidence_hash import sha

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():raise FileExistsError('Choose a new output file')
    f=pd.read_parquet(ROOT/'results/evaluation/protected_weather/weather_inputs.parquet')
    assert not {'road_temp','ice','observed_ice','target','state_raw'}&set(f)
    x=f[list(FEATURES)].copy();aws_valid=f.aws_age_minutes.between(0,60,inclusive='right')
    x.loc[~aws_valid,['aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint']]=np.nan
    records=json.loads((ROOT/'model/refit_receipt.json').read_text('utf8'))['models']
    hashes={r['name']:r['sha256'] for r in records}
    components=[]
    with threadpool_limits(limits=2):
        for name in ['weather12_mse300','weather12_mae300']:
            path=ROOT/'model'/(name+'.joblib');assert sha(path)==hashes[name]
            model=joblib.load(path);assert list(model.feature_names_in_)==list(FEATURES)
            components.append(model.predict(x))
    asos_valid=f.asos_age_minutes.between(0,60,inclusive='right')
    reference=np.mean(components,axis=0);reference[~asos_valid]=np.nan
    f['asos_air_temperature']=f.asos_air_temp.where(asos_valid)
    f['aws_air_temperature']=f.aws_air_temp.where(f.aws_age_minutes.between(0,15,inclusive='right')).fillna(f.asos_air_temperature)
    f['reference_temperature_12']=reference
    observed=pd.read_csv(ROOT/'results/evaluation/observations_predictions.csv',usecols=['station_id','prediction_time_kst','observed_road_temperature_c','estimated_road_temperature_c'],
        dtype={'station_id':str},parse_dates=['prediction_time_kst'],float_precision='round_trip').rename(columns={'station_id':'station','prediction_time_kst':'time'})
    f=f.merge(observed,on=['station','time'],validate='one_to_one')
    f['winter']=np.where(f.time.dt.month>=7,f.time.dt.year,f.time.dt.year-1)
    columns=['station','time','winter','observed_road_temperature_c','asos_air_temperature','aws_air_temperature','asos_ground_temp','reference_temperature_12','estimated_road_temperature_c']
    out=f[columns];a.output.parent.mkdir(parents=True,exist_ok=True);out.to_parquet(a.output,index=False,compression='zstd')
    print(json.dumps(dict(rows=len(out),fixed_models=2,training=False,threshold_selection=False),ensure_ascii=False))

if __name__=='__main__':main()
