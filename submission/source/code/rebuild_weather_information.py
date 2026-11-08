"""전체 실제 기상 입력의 중복을 검사하고 고정 모형으로 조건 노출을 재현한다."""
from pathlib import Path
import sys,json,argparse,hashlib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import joblib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.evidence_hash import sha
from src.submission_runtime import infer

FIELDS=['asos_air_temp','aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint',
    'aws_age_minutes','asos_age_minutes','hour_sin','hour_cos','season_sin','season_cos','rain15_max_3h','asos_snow_cm']

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():raise FileExistsError('Choose a new output directory')
    a.output.mkdir(parents=True)
    metadata=json.loads((ROOT/'model/refit_receipt.json').read_text('utf8'));hashes={r['name']:r['sha256'] for r in metadata['models']}
    models=[]
    for name in ['weather12_mse300','weather12_mae300']:
        path=ROOT/'model'/(name+'.joblib');assert sha(path)==hashes[name];models.append(joblib.load(path))
    source=ROOT/'data/icing_weather_inputs.parquet';parquet=pq.ParquetFile(source)
    buffers={};cache={};mapping=[];exposure=[];comparisons=0
    for number in range(parquet.num_row_groups):
        z=parquet.read_row_group(number).to_pandas()
        assert z.prediction_group.nunique()==1 and z.winter.nunique()==1
        group=str(z.prediction_group.iloc[0]);winter=int(z.winter.iloc[0])
        z=z.sort_values('time').reset_index(drop=True)
        calendar=pd.date_range(f'{winter}-11-01',f'{winter+1}-03-01',freq='10min',inclusive='left')
        assert pd.DatetimeIndex(z.time).equals(calendar)
        x=np.ascontiguousarray(z[FIELDS].to_numpy(dtype=np.float64));x[np.isnan(x)]=np.nan
        fingerprint=hashlib.sha256(x.tobytes()).hexdigest();key=f'{winter}_{fingerprint}'
        if key in buffers:
            assert np.array_equal(x,buffers[key],equal_nan=True);comparisons+=1
        else:
            buffers[key]=x
            frame=z[['time',*FIELDS]].copy();frame.insert(0,'station',group)
            result=infer(frame,models);valid=result.predicted_ice.notna()
            count=int(result.predicted_ice.eq(1).sum());denominator=int(valid.sum())
            cache[key]=dict(planned_slots=len(z),ice_valid_slots=denominator,cold_wet_slots=count,weather_index_100=100*(count/denominator))
        mapping.append(dict(winter=winter,prediction_group=group,weather_information_group=key,rows=len(z),input_sha256=fingerprint))
        exposure.append(dict(prediction_group=group,winter=winter,weather_information_group=key,**cache[key]))
        if (number+1)%34==0:print('WEATHER INPUT GROUP',number+1,'/',parquet.num_row_groups,flush=True)
    pd.DataFrame(mapping).to_csv(a.output/'weather_information_groups.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(exposure).to_csv(a.output/'exposure_by_input_group.csv',index=False,encoding='utf-8-sig')
    summary=dict(rows=parquet.metadata.num_rows,declared_groups=len(mapping),distinct_predictor_series=len(cache),
        exact_duplicate_array_comparisons=comparisons,predictor_columns=FIELDS,source_sha256=sha(source),
        actual_information_groups_by_winter={str(y):int(q.weather_information_group.nunique()) for y,q in pd.DataFrame(mapping).groupby('winter')},
        fitting=False,threshold_selection=False,road_observations_read=False)
    (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
