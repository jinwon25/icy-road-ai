"""공간 적용용 7 ASOS 입력을 구성하고 기존 23곳의 입력 28열을 전량 재현한다."""
from datetime import datetime,timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.blind_icing import normalize_weather
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from src.segment_exposure import WeatherOnlySources
from src.road_weather_points import RoadWeatherPoints,EXTRA_FIELDS
from src.road_weather_runtime import INPUT_COLUMNS
from scripts.evaluate_objective_icing import read,write,verify_preserved


def main():
    out=ROOT/'outputs/private/weather_mapping_inputs_20261031_v1'
    if out.exists():raise FileExistsError('Preserve weather mapping inputs')
    old=ROOT/'outputs/private/asos_training_parity_20261025_v1/asos_raw_fields.parquet'
    new=ROOT/'outputs/private/weather_mapping_asos_20261031_v2/asos_raw_fields.parquet'
    receipt=read(new.parent/'receipt.json');assert receipt['status']=='mapping_asos_requests_complete'
    assert sha(new)==receipt['data_sha256'] and receipt['expected_rows']==receipt['received_rows']==5762
    old_receipt=read(old.parent/'receipt.json');assert sha(old)==old_receipt['data_sha256']
    source=ROOT/'outputs/private/releases/20261007/outputs/private/point_sources'
    metadata=ROOT/'outputs/private/weather_network_review_20261010_v1/metadata_analysis/development_points.csv'
    data=ROOT/'outputs/private/road_weather_targets_20261031_v3/development.parquet'
    assert sha(data)==read(data.parent/'receipt.json')['data_sha256']
    frozen=verify_preserved();out.mkdir(parents=True)
    paths=[old,new,new.parent/'receipt.json',metadata,data,Path(__file__),ROOT/'src/road_weather_points.py',
           ROOT/'src/thermal_weather_points.py',ROOT/'src/segment_exposure.py',ROOT/'src/solar_terrain.py']
    paths += [source/name for name in ['aws.parquet','asos.parquet','weather_coordinates.csv']]
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    write(out/'plan.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),signatures=signatures,preservation=frozen,
        scope='Pure weather input parity before projecting three new regressors to archived 500m segment midpoints',
        no_new_road_outcomes_read=True,existing_models_changed=False))
    raw=pd.concat([pd.read_parquet(old),pd.read_parquet(new)],ignore_index=True)
    extra=normalize_weather(raw);assert not extra.duplicated(['station','source_time']).any()
    assert set(extra.station)=={'140','146','172','243','245','248','251'}
    extra.to_parquet(out/'asos_supplementary.parquet',index=False,compression='zstd')
    weather=WeatherOnlySources(pd.read_parquet(source/'aws.parquet'),pd.read_parquet(source/'asos.parquet'),
        pd.read_csv(source/'weather_coordinates.csv',dtype={'station_id':str}))
    points=pd.read_csv(metadata,dtype={'station':str}).set_index('station')
    reference=pd.read_parquet(data,columns=['station','time']+INPUT_COLUMNS)
    records=[];values=0;maximum=0.
    with deny_network() as attempts:
        for station,q in reference.groupby('station',sort=True):
            q=q.sort_values('time').reset_index(drop=True);p=points.loc[station]
            frame,mapping=RoadWeatherPoints(weather,extra,pd.DatetimeIndex(q.time)).build(p.lat,p.lon)
            a=frame[INPUT_COLUMNS].to_numpy(float);b=q[INPUT_COLUMNS].to_numpy(float)
            np.testing.assert_allclose(a,b,atol=1e-10,rtol=0,equal_nan=True)
            error=float(np.nanmax(abs(a-b)));maximum=max(maximum,error);values+=a.size
            records.append(dict(station=station,rows=len(q),maximum_absolute_difference=error,**mapping))
            print('POINT INPUT PARITY',station,len(q),flush=True)
    assert not attempts and verify_preserved()==frozen
    write(out/'receipt.json',dict(status='weather_mapping_inputs_verified',source_signatures=signatures,
        supplementary_sha256=sha(out/'asos_supplementary.parquet'),extra_columns=EXTRA_FIELDS,
        checked_stations=len(records),checked_values=values,maximum_absolute_difference=maximum,
        points=records,protected_outcomes_read=False,network_attempts=0,preservation=frozen))
    print('MAPPING INPUTS VERIFIED',values,maximum,flush=True)


if __name__=='__main__':main()
