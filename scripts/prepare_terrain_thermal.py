"""허용 개발 지점의 좌표와 보존된 공개 DSM만 추가한다. 노면 정답은 변경하지 않는다."""
import json
from pathlib import Path
import sys
import pandas as pd
ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0, str(ROOT))
from src.solar_terrain import CopernicusSampler
from src.terrain_thermal import solar_terrain_inputs
from src.two_winter import validate
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation


def main():
    private = ROOT / 'outputs/private';out = private / 'terrain_thermal_data_20261024_v1'
    if out.exists():
        raise FileExistsError('Preserve terrain inputs')
    frozen = preservation()
    source = private / 'canonical_thermal_data_20261024_v1/development.parquet'
    assert sha(source) == json.loads((source.parent/'receipt.json').read_text('utf-8'))['data_sha256']
    data = validate(pd.read_parquet(source)).sort_values(['station','time']).reset_index(drop=True)
    metadata = private / 'weather_network_review_20261010_v1/metadata_analysis/development_points.csv'
    coords = pd.read_csv(metadata, dtype={'station':str}).set_index('station')
    assert set(coords.index) == set(data.station)
    folder = private / 'releases/20261007/outputs/private/external/copernicus_dem'
    tiles = sorted(folder.glob('*.tif'));assert len(tiles) == 4
    license_path = folder/'eula_F.pdf'
    assert sha(license_path) == '32049914c37f14e7d53b48d13d74a49e77c030236e2acc7a0df426f9344feba2'
    static=[];parts=[]
    with deny_network() as attempts:
        sampler=CopernicusSampler(tiles)
        for station, part in data.groupby('station',sort=True):
            c=coords.loc[station];terrain=sampler.features(c.lon,c.lat)
            if terrain['dsm_valid_fraction_500m'] != 1.:
                raise ValueError('Incomplete local terrain coverage')
            static.append(dict(station=station,lat=c.lat,lon=c.lon,**terrain))
            inputs=solar_terrain_inputs(part.time,c.lat,c.lon,terrain);inputs.index=part.index
            parts.append(inputs)
    added=pd.concat(parts).reindex(data.index)
    assert not set(added)&set(data)
    result=pd.concat([data,added],axis=1)
    pd.testing.assert_frame_equal(result[data.columns],data,check_exact=True)
    assert not attempts and preservation()==frozen
    out.mkdir();result.to_parquet(out/'development.parquet',index=False,compression='zstd')
    pd.DataFrame(static).to_csv(out/'station_terrain.csv',index=False)
    attribution='produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.'
    disclaimer='The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30.'
    (out/'COPERNICUS_NOTICE.txt').write_text(attribution+'\n\n'+disclaimer+'\n','utf-8')
    receipt=dict(status='terrain_weather_inputs_prepared',rows=len(data),stations=len(static),
        added_features=list(added),data_sha256=sha(out/'development.parquet'),
        source_sha256=sha(source),metadata_sha256=sha(metadata),protected_labels_read=False,
        old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],network_attempts=0,
        attribution=attribution,disclaimer=disclaimer,
        limitations=['Surface model includes buildings and canopy; not road deck elevation.',
                     '16-direction, 3-km horizon approximation; no pavement, bridge or deicing labels.',
                     'Astronomical proxy is not a measured radiation flux.'],
        source_signatures={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'src/solar_terrain.py',ROOT/'src/terrain_thermal.py',license_path,*tiles]})
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='source_signatures'},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
