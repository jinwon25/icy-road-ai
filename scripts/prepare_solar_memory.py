"""공개 기상 관측소 좌표의 태양 위치를 더하고 지점 좌표 방식과 대조한다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.solar_terrain import solar_position
from src.weather_features import haversine_km
from src.two_winter import validate
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation


def main():
    private=ROOT/'outputs/private';out=private/'solar_memory_data_20261024_v1'
    if out.exists():raise FileExistsError('Preserve solar memory data')
    frozen=preservation();source=private/'canonical_thermal_data_20261024_v1/development.parquet'
    assert sha(source)==json.loads((source.parent/'receipt.json').read_text('utf-8'))['data_sha256']
    f=validate(pd.read_parquet(source));original=f.copy()
    metadata=private/'weather_network_review_20261010_v1/metadata_analysis/development_points.csv'
    targets=pd.read_csv(metadata,dtype={'station':str}).set_index('station')
    cache=private/'releases/20261007/outputs/private/point_sources'
    ids=set(pd.read_parquet(cache/'asos.parquet',columns=['station']).station.astype(str))
    coords=pd.read_csv(cache/'weather_coordinates.csv',dtype={'station_id':str})
    coords=coords.loc[coords.kind.eq('ASOS')&coords.station_id.isin(ids)]
    mapping=[]
    for station,part in f.groupby('station',sort=True):
        c=targets.loc[station]
        distance,sid=min((haversine_km(c.lat,c.lon,r.latitudes,r.longitudes),r.station_id) for r in coords.itertuples())
        selected=coords.set_index('station_id').loc[sid]
        np.testing.assert_allclose(part.asos_distance_km,distance,rtol=0,atol=1e-10)
        for prefix,lat,lon in [('asos_',selected.latitudes,selected.longitudes),('',c.lat,c.lon)]:
            altitude,_=solar_position(part.time,lat,lon)
            f.loc[part.index,prefix+'solar_altitude_deg']=altitude
            f.loc[part.index,prefix+'solar_sine_positive']=np.maximum(0,np.sin(np.deg2rad(altitude)))
        mapping.append(dict(station=station,asos_station=sid,asos_lat=selected.latitudes,asos_lon=selected.longitudes))
    pd.testing.assert_frame_equal(f[original.columns],original,check_exact=True)
    assert preservation()==frozen
    out.mkdir();f.to_parquet(out/'development.parquet',index=False,compression='zstd')
    pd.DataFrame(mapping).to_csv(out/'station_solar_coordinates.csv',index=False)
    result=dict(status='solar_memory_inputs_prepared',data_sha256=sha(out/'development.parquet'),rows=len(f),
        protected_labels_read=False,source_sha256=sha(source),old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],
        source_signatures={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),metadata,cache/'weather_coordinates.csv',ROOT/'src/solar_terrain.py']},
        interpretation='Astronomical features at either the target or its actual nearest ASOS location. Not a measured radiation flux. No DSM features in this comparison.')
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n','utf-8');print(result,flush=True)

if __name__=='__main__':main()
