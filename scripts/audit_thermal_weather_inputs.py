"""실제 배포 원천의 기상만 재조회해 23개 개발 지점의 열 입력을 교차 검산한다."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.thermal_weather_points import ThermalWeatherPoints
from src.segment_exposure import WeatherOnlySources
from src.temperature_transfer import THERMAL_FEATURES
from src.two_winter import validate
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation
from src.offline_runtime import deny_network


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=ROOT/'outputs/private/extended_thermal_data_20261024_v1/development.parquet')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/private/thermal_weather_input_audit_20261024_v1')
    args=parser.parse_args()
    private=ROOT/'outputs/private';out=args.output.resolve()
    if out.exists():raise FileExistsError('Preserve input audit')
    frozen=preservation();path=args.data.resolve()
    data=validate(pd.read_parquet(path,columns=['station','time','winter',*THERMAL_FEATURES]))
    metadata=private/'weather_network_review_20261010_v1/metadata_analysis/development_points.csv'
    coords=pd.read_csv(metadata,dtype={'station':str}).set_index('station')
    cache=private/'releases/20261007/outputs/private/point_sources'
    weather=WeatherOnlySources(pd.read_parquet(cache/'aws.parquet'),pd.read_parquet(cache/'asos.parquet'),
        pd.read_csv(cache/'weather_coordinates.csv',dtype={'station_id':str}))
    records=[]
    with deny_network() as attempts:
        for (station,winter),part in data.groupby(['station','winter']):
            part=part.sort_values('time');c=coords.loc[station]
            actual,_=ThermalWeatherPoints(weather,pd.DatetimeIndex(part.time)).build(c.lat,c.lon)
            for col in THERMAL_FEATURES:
                a=actual[col].to_numpy(float);b=part[col].to_numpy(float)
                mismatch=~np.isclose(a,b,rtol=0,atol=1e-10,equal_nan=True)
                records.append(dict(station=station,winter=int(winter),column=col,rows=len(part),mismatches=int(mismatch.sum()),
                    max_abs_difference=float(np.nanmax(np.abs(a-b))) if np.isfinite(a-b).any() else None))
    table=pd.DataFrame(records);out.mkdir();table.to_csv(out/'comparison.csv',index=False)
    assert preservation()==frozen and not attempts
    result=dict(status='passed' if table.mismatches.sum()==0 else 'mismatches_need_investigation',
        compared_values=int(table.rows.sum()),mismatches=int(table.mismatches.sum()),protected_labels_read=False,
        any_outcome_columns_read=False,network_attempts=len(attempts),
        signatures={str(p.relative_to(ROOT)):sha(p) for p in [path,metadata,*[cache/n for n in ['aws.parquet','asos.parquet','weather_coordinates.csv']],
        Path(__file__),ROOT/'src/thermal_weather_points.py',ROOT/'src/segment_exposure.py']})
    (out/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    if result['mismatches']:raise AssertionError('Thermal source reconstruction differs')

if __name__=='__main__':main()
