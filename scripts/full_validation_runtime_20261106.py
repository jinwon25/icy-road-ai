"""포함된 전 기간 기상으로 모델을 실행하고 제출 예측 열과 대조한다."""
from pathlib import Path
import argparse,json,subprocess,sys,os,time
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    if a.output.exists():raise FileExistsError('새 출력 폴더를 지정하세요.')
    a.output.mkdir(parents=True)
    target=a.output.resolve()/'predictions.parquet'
    env=dict(os.environ);env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',LOKY_MAX_CPU_COUNT='2')
    started=time.perf_counter()
    command=[sys.executable,'-X','utf8','code/predict.py','--input','data/validation_weather.parquet','--output',str(target)]
    r=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf8',timeout=600)
    seconds=time.perf_counter()-started
    if r.returncode:raise RuntimeError(r.stdout+r.stderr)
    (a.output/'cli_stdout.json').write_text(r.stdout,'utf8')
    f=pd.read_parquet(target)
    reference=pd.read_csv(ROOT/'results/evaluation/observations_predictions.csv',
        usecols=['station_id','prediction_time_kst','estimated_road_temperature_c','predicted_ice'],
        dtype={'station_id':str},parse_dates=['prediction_time_kst'],float_precision='round_trip')
    reference=reference.rename(columns={'station_id':'station','prediction_time_kst':'time','estimated_road_temperature_c':'estimated_road_temp_c'})
    columns=['station','time','estimated_road_temp_c','predicted_ice']
    pair=f[columns].merge(reference,on=['station','time'],validate='one_to_one',suffixes=['','_expected'])
    assert len(pair)==len(f)==len(reference)==103680
    for c in columns[2:]:np.testing.assert_array_equal(pair[c].to_numpy(float,na_value=np.nan),pair[c+'_expected'].to_numpy(float,na_value=np.nan))
    receipt=dict(status='full_validation_predictions_exact',rows=len(f),temperature_available=int(f.estimated_road_temp_c.notna().sum()),
        icing_available=int(f.predicted_ice.notna().sum()),observed_target_columns_read=False,
        model_fits=0,threshold_searches=0,wall_seconds=seconds)
    (a.output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
