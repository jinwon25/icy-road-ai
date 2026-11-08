"""현재 기온·습도·풍속 모형의 출력을 구간 키와 시각으로 결합한다."""
from pathlib import Path
import argparse,subprocess,sys,tempfile,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ['input','aws-input','points','output']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--output-start');p.add_argument('--output-end');a=p.parse_args()
 if a.output.exists():raise FileExistsError('Choose a new output file')
 with tempfile.TemporaryDirectory(prefix='road_weather_') as tmp:
  tmp=Path(tmp);humidity=tmp/'humidity.csv';wind=tmp/'wind.csv'
  cmd=[sys.executable,'-X','utf8',str(ROOT/'weather/humidity/scripts/predict_weather_history.py'),'--input',str(a.input.resolve()),'--output',str(humidity)]
  for key,value in [('--output-start',a.output_start),('--output-end',a.output_end)]:
   if value:cmd.extend([key,value])
  subprocess.run(cmd,check=True)
  subprocess.run([sys.executable,'-X','utf8',str(ROOT/'weather/wind/scripts/predict_wind_network.py'),'--bundle',str(ROOT/'weather/wind'),'--input',str(a.input.resolve()),'--aws-input',str(a.aws_input.resolve()),'--points',str(a.points.resolve()),'--output',str(wind)],check=True)
  opt=dict(dtype={'station':str},parse_dates=['time'],float_precision='round_trip')
  h=pd.read_csv(humidity,**opt);w=pd.read_csv(wind,**opt)
  keep=['station','time','estimated_air_temperature_c','estimated_humidity_pct','estimated_air_temperature_c_available','estimated_humidity_pct_available']
  out=h[keep].merge(w[['station','time','estimated_wind_speed_ms','estimated_wind_speed_ms_available']],on=['station','time'],validate='one_to_one',how='left')
  if a.output_start:out=out.loc[out.time.ge(pd.Timestamp(a.output_start))]
  if a.output_end:out=out.loc[out.time.lt(pd.Timestamp(a.output_end))]
  if out.empty:raise ValueError('Empty output period')
  a.output.parent.mkdir(parents=True,exist_ok=True);out.to_csv(a.output,index=False,encoding='utf-8-sig')
 print(json.dumps(dict(rows=len(out),fields=['air_temperature','humidity','wind_speed']),ensure_ascii=False))
if __name__=='__main__':main()
