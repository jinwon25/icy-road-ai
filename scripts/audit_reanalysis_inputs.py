"""기상 원문·과거 연결·이력을 별도 NumPy 집계로 대조하고 기존 정답 보존을 확인한다."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.fetch_reanalysis_inputs import read,write
from scripts.evaluate_objective_icing import verify_preserved
from src.data_source import sha256_file as sha


def main():
    folder=ROOT/'outputs/private/era5_land_inputs_20261031_v1';out=ROOT/'outputs/private/reanalysis_development_20261031_v1'
    target=out/'independent_verification.json'
    if target.exists():raise FileExistsError('Preserve first audit')
    receipt=read(out/'receipt.json');manifest=read(folder/'request_manifest.json')
    assert sha(out/'development.parquet')==receipt['data_sha256'] and sha(out/'grid_mapping.csv')==receipt['grid_mapping_sha256']
    assert sha(folder/'request_manifest.json')==receipt['source_manifest_sha256']
    for name,digest in receipt['source_signatures'].items():assert sha(ROOT/name)==digest,name
    source=ROOT/receipt['original_source'];assert sha(source)==receipt['original_sha256']
    original=pd.read_parquet(source).sort_values(['station','time']).reset_index(drop=True)
    f=pd.read_parquet(out/'development.parquet');pd.testing.assert_frame_equal(f[original.columns],original,check_exact=True)
    hours=pd.read_parquet(folder/'hourly.parquet');assert sha(folder/'hourly.parquet')==receipt['weather_sha256']
    counts=0;raw_count=0;largest=0.
    for record in manifest['records'].values():
        params=record['params'];station=record['quality']['station'];start=params['start_date'];end=params['end_date']
        path=folder/(station+'_'+start[:4]+'.json');assert sha(path)==record['sha256']
        payload=read(path);h=payload['hourly'];times=pd.DatetimeIndex(h['time'])
        assert payload['utc_offset_seconds']==32400 and params['models']=='era5_land' and params['elevation']=='nan'
        q=f.loc[f.station.eq(station)&f.time.ge(start)&f.time.lt(pd.Timestamp(end)+pd.Timedelta(days=1))]
        ids=np.searchsorted(times.to_numpy(),q.time.to_numpy(),side='left')-1
        assert (ids>=0).all()
        np.testing.assert_array_equal(times.to_numpy()[ids],q.era5_source_time.to_numpy())
        raw=hours.loc[hours.station.eq(station)&hours.source_time.ge(start)&hours.source_time.le(end+' 23:00')]
        np.testing.assert_array_equal(raw.source_time.to_numpy(),times.to_numpy())
        for column in manifest['variables']:
            a=np.array(h[column],float)
            np.testing.assert_array_equal(a,raw[column].to_numpy());raw_count+=len(a)
            np.testing.assert_array_equal(a[ids],q['era5_'+column].to_numpy());counts+=len(q)
            if column in ['temperature_2m','soil_temperature_0_to_7cm','soil_moisture_0_to_7cm','snow_depth']:
                for window in [6,24,72]:
                    # 각 구간의 이동 창을 직접 구성한다. pandas rolling 구현은 사용하지 않는다.
                    windows=np.lib.stride_tricks.sliding_window_view(a,window)
                    expected=np.r_[np.full(window-1,np.nan),windows.mean(axis=1)][ids]
                    actual=q['era5_'+column+'_mean'+str(window)+'h'].to_numpy()
                    np.testing.assert_allclose(expected,actual,rtol=0,atol=1e-10,equal_nan=True)
                    largest=max(largest,float(np.nanmax(np.abs(expected-actual))));counts+=len(q)
    assert verify_preserved()==receipt['preservation']
    write(target,dict(status='passed',raw_files=len(manifest['records']),raw_values=raw_count,
        joined_feature_values=counts,maximum_history_difference=largest,original_rows_preserved=len(f),
        data_sha256=receipt['data_sha256'],receipt_sha256=sha(out/'receipt.json'),audit_script_sha256=sha(Path(__file__)),
        protected_labels_read=False,new_road_labels_used=False,retrospective_only=True))
    print('AUDIT PASSED',raw_count,'source values',counts,'joined values',flush=True)


if __name__=='__main__':main()
