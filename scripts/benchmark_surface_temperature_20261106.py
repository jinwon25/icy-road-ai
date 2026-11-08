"""고정한 노면온도 모형과 단순 기온·지면온도·12특성 회귀를 같은 관측쌍에서 비교한다."""
from pathlib import Path
import sys,json,joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.assess_protected_weather_20261106 import validate_seal,evaluate,resampling,OUT,STATIONS
from scripts.seal_protected_weather_20261106 import W,B,write
from src.submission_runtime import FEATURES
from src.data_source import sha256_file as sha

def main():
    O=W/'temperature_benchmarks';O.mkdir()
    seal=validate_seal()
    write(O/'plan.json',dict(protected_temperature_previously_opened=True,training=False,selection=False,
        purpose='고정된 최종 회귀의 실제 추가 가치를 서로 다른 강도의 참조 기준과 비교',
        methods=['ASOS air','nearest AWS air or ASOS','ASOS ground temperature','frozen 12-feature paired regression','current 63-feature regression'],
        metrics=['bias','mae','rmse'],near_freezing='observed road temperature between -2 and +2 Celsius inclusive',
        aggregation='common finite pairs across all 5 methods; equal site macro',
        resampling='2000 paired 7-day circular date blocks, synchronised across sites within each winter; seed 61107',
        protected_weather_prediction_seal_sha256=seal))
    f=pd.read_parquet(OUT/'weather_inputs.parquet')
    x=f[list(FEATURES)].copy();stale=~f.aws_age_minutes.between(0,60,inclusive='right')
    x.loc[stale,['aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint']]=np.nan
    with threadpool_limits(limits=2):
        temp=np.mean([joblib.load(B/'model'/(name+'.joblib')).predict(x) for name in ['weather12_mse300','weather12_mae300']],axis=0)
    temp[~f.asos_age_minutes.between(0,60,inclusive='right')]=np.nan
    f['reference_temperature_12']=temp
    weather=pd.read_parquet(OUT/'predictions.parquet')
    f=f.merge(weather[['station','time','asos_air_temperature','aws_air_temperature']],on=['station','time'],validate='one_to_one')
    surface_path=B/'results/evaluation/observations_predictions.csv'
    actual=pd.read_csv(surface_path,dtype={'station_id':str},parse_dates=['prediction_time_kst'],float_precision='round_trip')
    actual=actual.rename(columns={'station_id':'station','prediction_time_kst':'time'})
    f=f.merge(actual[['station','time','observed_road_temperature_c','estimated_road_temperature_c']],on=['station','time'],validate='one_to_one')
    f['winter']=np.where(f.time.dt.month>=7,f.time.dt.year,f.time.dt.year-1)
    methods={'asos_air_reference':'asos_air_temperature','aws_air_reference':'aws_air_temperature',
        'asos_ground_reference':'asos_ground_temp','weather12_regression':'reference_temperature_12','estimated':'estimated_road_temperature_c'}
    target='observed_road_temperature_c';metrics=[]
    for scope,q in [('all_temperature',f),('near_freezing_observed_pm2c',f.loc[f[target].between(-2,2)])]:
        metrics.extend([dict(temperature_scope=scope,**r) for r in evaluate(q,target,methods)])
    uncertainty=resampling(f,target,methods,np.random.default_rng(61107))
    pd.DataFrame(metrics).to_csv(O/'metrics.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(uncertainty).to_csv(O/'paired_day_block_sensitivity.csv',index=False,encoding='utf-8-sig')
    f[['station','time','winter',target,*methods.values()]].to_parquet(O/'observations_predictions.parquet',index=False,compression='zstd')
    values=[r for r in metrics if r['station']=='station_macro' and r['period']=='all']
    write(O/'summary.json',dict(status='fixed_temperature_benchmarks_computed',metrics=values,uncertainty=uncertainty,
        current_predictions_changed=False,source_sha256=sha(surface_path),prediction_seal_sha256=validate_seal()))
    print(json.dumps(values,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
