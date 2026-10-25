"""연결 ASOS 좌표의 태양 위치만 더해 기존 138개 기상 그룹을 정확하게 유지한다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.solar_terrain import solar_position
from src.solar_thermal_runtime import temperature_predictors
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation


def main():
    private=ROOT/'outputs/private';out=private/'solar_delivery_inputs_20261024_v1'
    if out.exists():raise FileExistsError('Preserve completed solar input preparation')
    source=private/'extended_delivery_inputs_20261024_v2';receipt=json.loads((source/'receipt.json').read_text('utf-8'))
    coordinates=private/'releases/20261007/outputs/private/point_sources/weather_coordinates.csv'
    coords=pd.read_csv(coordinates,dtype={'station_id':str});coords=coords.loc[coords.kind.eq('ASOS')].set_index('station_id')
    frozen=preservation();out.mkdir();(out/'weather_groups').mkdir();groups={}
    for group,record in receipt['groups'].items():
        path=source/'weather_groups'/(group+'.parquet');assert sha(path)==record['weather_sha256']
        f=pd.read_parquet(path);original=f.copy();c=coords.loc[record['asos_station']]
        altitude,_=solar_position(f.time,c.latitudes,c.longitudes)
        f['asos_solar_altitude_deg']=altitude;f['asos_solar_sine_positive']=np.maximum(0,np.sin(np.deg2rad(altitude)))
        pd.testing.assert_frame_equal(f[original.columns],original,check_exact=True)
        x,valid,_=temperature_predictors(f,'combined_asos_solar');assert len(x.columns)==63
        target=out/'weather_groups'/(group+'.parquet');f.to_parquet(target,index=False,compression='zstd')
        groups[group]=dict(record,weather_sha256=sha(target),thermal_source_sha256=record['weather_sha256'],
            solar_coordinate_source='asos_station',solar_lat=float(c.latitudes),solar_lon=float(c.longitudes),temperature_valid_rows=int(valid.sum()))
        if len(groups)%30==0:print('solar delivery inputs',len(groups),'/',len(receipt['groups']),flush=True)
    assert preservation()==frozen
    result=dict(status='asos_solar_delivery_inputs_verified',group_count=len(groups),rows=sum(v['rows'] for v in groups.values()),
        existing_thermal_values_changed=0,protected_labels_read=False,groups=groups,
        old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],
        signatures={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),source/'receipt.json',coordinates,ROOT/'src/solar_terrain.py',ROOT/'src/solar_thermal_runtime.py']})
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print({k:v for k,v in result.items() if k not in ['groups','signatures']},flush=True)

if __name__=='__main__':main()
