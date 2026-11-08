"""완료한 ERA5-Land 원문을 기존 개발 자료에 과거 시각으로만 연결한다."""
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.fetch_reanalysis_inputs import read,write
from scripts.evaluate_objective_icing import verify_preserved
from src.reanalysis_inputs import histories,FIELDS
from src.weather_features import prior_join
from src.data_source import sha256_file as sha


def main():
    folder=ROOT/'outputs/private/era5_land_inputs_20261031_v1';out=ROOT/'outputs/private/reanalysis_development_20261031_v1'
    if out.exists():raise FileExistsError('Preserve prepared inputs')
    manifest=read(folder/'request_manifest.json');assert manifest['status']=='complete'
    assert sha(folder/'hourly.parquet')==manifest['hourly_sha256']
    plan=read(folder/'plan.json');frozen=verify_preserved()
    for name,digest in plan['signatures'].items():assert sha(ROOT/name)==digest,name
    source=ROOT/'outputs/private/solar_memory_data_20261024_v1/development.parquet'
    original=pd.read_parquet(source).sort_values(['station','time']).reset_index(drop=True)
    weather=pd.read_parquet(folder/'hourly.parquet')
    assert len(set(original.station))==23 and set(original.station)==set(weather.station)
    assert not set(original.station)&set(plan['settings']['blocked_stations'])
    weather=histories(weather);parts=[]
    for station,q in original.groupby('station',sort=True):
        parts.append(prior_join(q,weather.loc[weather.station.eq(station)].drop(columns='station'),'era5'))
    combined=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(combined[original.columns],original,check_exact=True)
    columns=['era5_'+c for c in weather if c not in ['station','source_time']]
    assert combined[columns].notna().all().all(),'Incomplete research inputs; preserve original denominator'
    assert combined.era5_age_minutes.between(0,60,inclusive='right').all()
    out.mkdir();combined.to_parquet(out/'development.parquet',index=False,compression='zstd')
    metadata=pd.DataFrame([v['quality'] for v in manifest['records'].values()])
    grid=metadata[['station','requested_lat','requested_lon','grid_lat','grid_lon','grid_distance_km']].drop_duplicates()
    assert not grid.station.duplicated().any()
    grid.to_csv(out/'grid_mapping.csv',index=False,encoding='utf-8-sig')
    assert verify_preserved()==frozen
    write(out/'receipt.json',dict(status='prepared_pending_independent_audit',rows=len(combined),stations=23,
        weather_grid_count=len(grid[['grid_lat','grid_lon']].drop_duplicates()),raw_features=['era5_'+c for c in FIELDS],
        memory_features=columns,data_sha256=sha(out/'development.parquet'),grid_mapping_sha256=sha(out/'grid_mapping.csv'),
        original_source=source.relative_to(ROOT).as_posix(),original_sha256=sha(source),
        weather_sha256=manifest['hourly_sha256'],source_manifest_sha256=sha(folder/'request_manifest.json'),
        source_signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),ROOT/'src/reanalysis_inputs.py',ROOT/'src/weather_features.py']},
        preservation=frozen,retrospective_only=True,new_road_labels_used=False))
    print('PREPARED',len(combined),'rows',len(columns),'ERA5-Land features',flush=True)


if __name__=='__main__':main()
