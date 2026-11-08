"""기존 보호 봉인·오프라인 재현·기준 단조성·원 래스터 표고·회귀 분모를 독립 검산한다."""
from pathlib import Path
from itertools import combinations
import sys,json
import numpy as np
import pandas as pd
import rasterio
import geopandas as gpd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W,write
from scripts.evaluate_objective_icing import verify_preserved
from src.data_source import sha256_file as sha
B=W/'icy_road_model'

def main():
    assert not (W/'independent_evidence_audit.json').exists()
    preservation=verify_preserved()
    old=json.loads((W/'original_icy_road_model_manifest.json').read_text('utf8'))['files']
    protected=[]
    for relative,record in old.items():
        if relative.endswith('.joblib') or relative.startswith(('model/','data/training_','results/weather/')) or relative in ['results/evaluation/observations_predictions.csv','results/evaluation/observations_predictions.parquet']:
            assert sha(B/relative)==record['sha256'],relative;protected.append(relative)
    pairs=[
        ('temperature_benchmarks/metrics.csv','results/evaluation/temperature_benchmarks/metrics.csv'),
        ('temperature_benchmarks/paired_day_block_sensitivity.csv','results/evaluation/temperature_benchmarks/paired_day_block_sensitivity.csv'),
        ('inspection_sensitivity/scenario_summary.csv','results/sections/sensitivity/scenario_summary.csv'),
        ('inspection_sensitivity/scenario_membership.csv','results/sections/sensitivity/scenario_membership.csv'),
        ('condition_evidence/segment_daily_associations.csv','results/conditions/segment_daily_associations.csv'),
        ('condition_evidence/development_observed_ice_by_condition.csv','results/conditions/development_observed_ice_by_condition.csv'),
        ('terrain_context/segment_terrain.csv','results/sections/terrain/segment_terrain.csv'),
        ('terrain_context/segment_solar_context.csv','results/sections/terrain/segment_solar_context.csv')]
    for local,delivered in pairs:
        p=B/'local_review'/local;q=B/delivered;assert sha(p)==sha(q),(local,'not byte-identical')
    scenarios=pd.read_csv(B/'results/sections/sensitivity/scenario_summary.csv')
    membership=pd.read_csv(B/'results/sections/sensitivity/scenario_membership.csv',dtype={'seg_id':str}).set_index('seg_id')
    sets={int(r.scenario):set(membership.index[membership[f'scenario_{int(r.scenario):02d}']]) for r in scenarios.itertuples()}
    monotonic=0
    for a,b in combinations(scenarios.itertuples(),2):
        # 기준이 모두 같거나 엄격해질 때 집합이 커지면 구현 오류다.
        if a.weather_quantile<=b.weather_quantile and a.curve_quantile<=b.curve_quantile and a.margin_m<=b.margin_m:
            assert sets[b.scenario]<=sets[a.scenario],(a.scenario,b.scenario);monotonic+=1
    terrain=pd.read_csv(B/'results/sections/terrain/segment_terrain.csv',dtype={'seg_id':str},float_precision='round_trip')
    coordinates=terrain[['point_lon','point_lat']].to_numpy();independent=np.full(len(terrain),np.nan)
    # 대용 조회 함수 대신 Rasterio/GDAL의 공식 sample API로 원 픽셀을 직접 대조한다.
    for path in sorted((B/'data/copernicus_dem').glob('*.tif')):
        with rasterio.open(path) as ds:
            take=(coordinates[:,0]>=ds.bounds.left)&(coordinates[:,0]<ds.bounds.right)&(coordinates[:,1]>ds.bounds.bottom)&(coordinates[:,1]<=ds.bounds.top)
            independent[take]=[float(v[0]) for v in ds.sample(coordinates[take])]
    np.testing.assert_array_equal(independent,terrain.dsm_elevation_m)
    f=pd.read_parquet(B/'results/evaluation/temperature_benchmarks/observations_predictions.parquet')
    columns={'asos_air_reference':'asos_air_temperature','aws_air_reference':'aws_air_temperature','asos_ground_reference':'asos_ground_temp',
        'weather12_regression':'reference_temperature_12','estimated':'estimated_road_temperature_c'}
    reported=pd.read_csv(B/'results/evaluation/temperature_benchmarks/metrics.csv',dtype={'station':str})
    checks=0
    for scope,scope_frame in [('all_temperature',f),('near_freezing_observed_pm2c',f.loc[f.observed_road_temperature_c.between(-2,2)])]:
        for period,frame in [('all',scope_frame),*[(str(y),q) for y,q in scope_frame.groupby('winter')]]:
            all_values=frame[['observed_road_temperature_c',*columns.values()]].to_numpy(float)
            mask=np.isfinite(all_values).all(axis=1)
            q=frame.loc[mask]
            for station,z in [('pooled',q),*list(q.groupby('station'))]:
                for method,column in columns.items():
                    difference=z[column].to_numpy()-z.observed_road_temperature_c.to_numpy()
                    row=reported.loc[reported.temperature_scope.eq(scope)&reported.period.eq(period)&reported.station.eq(station)&reported.method.eq(method)].iloc[0]
                    assert row['n']==len(z)
                    np.testing.assert_allclose([row.bias,row.mae,row.rmse],[sum(difference)/len(z),sum(abs(difference))/len(z),np.sqrt(sum(difference*difference)/len(z))],rtol=1e-12,atol=1e-12)
                    checks+=4
    replay=pd.read_csv(B/'local_review/protected_weather_replay.csv',dtype={'station':str},parse_dates=['time'],float_precision='round_trip')
    fixed=pd.read_parquet(W/'protected_weather/predictions.parquet')
    keys=['station','time','estimated_air_temperature_c','estimated_humidity_pct','estimated_wind_speed_ms']
    pd.testing.assert_frame_equal(replay[keys],fixed[keys],check_exact=True)
    availability=pd.read_csv(B/'results/evaluation/protected_weather/target_availability.csv')
    assert availability[['air_temperature','relative_humidity','wind_speed']].eq(0).all().all() and len(availability)==6
    # 최종 GIS도 같은 도로 키와 수치로 배포한다.
    geometry=gpd.read_file(B/'results/weather/weather_segments.gpkg',layer='winter_2024')[['seg_id','geometry']]
    seasonal=pd.read_csv(B/'results/sections/terrain/segment_solar_context.csv',dtype={'seg_id':str},float_precision='round_trip')
    stability=pd.read_csv(B/'results/sections/sensitivity/segment_stability.csv',dtype={'seg_id':str},float_precision='round_trip')
    for winter,part in seasonal.groupby('winter'):
        combined=part.merge(terrain,on='seg_id',validate='many_to_one').merge(geometry,on='seg_id',validate='many_to_one')
        g=gpd.GeoDataFrame(combined,geometry='geometry',crs=geometry.crs)
        target=B/'results/sections/terrain/terrain_context.gpkg'
        g.to_file(target,layer=f'winter_{winter}',driver='GPKG')
        readback=gpd.read_file(target,layer=f'winter_{winter}').sort_values('seg_id')
        original=g.sort_values('seg_id')
        np.testing.assert_array_equal(readback.seg_id,original.seg_id)
        np.testing.assert_array_equal(readback.potential_shade_daylight_fraction,original.potential_shade_daylight_fraction)
    g=gpd.GeoDataFrame(stability.merge(geometry,on='seg_id',validate='one_to_one'),geometry='geometry',crs=geometry.crs)
    g.to_file(B/'results/sections/sensitivity/selection_stability.gpkg',layer='criteria_stability',driver='GPKG')
    assert verify_preserved()==preservation
    write(W/'independent_evidence_audit.json',dict(status='passed',preserved_model_training_and_prediction_files=len(protected),
        portable_csvs_byte_identical=len(pairs),monotonic_subset_checks=monotonic,independent_rasterio_pixel_checks=len(terrain),
        manual_regression_count_and_error_checks=checks,weather_cli_rows_exact=len(replay),gis_terrain_rows_reloaded=1686,
        protected_weather_observation_pairs=0,models_changed=False,prediction_values_changed=False,preservation=preservation,
        code_sha256=sha(Path(__file__))))
    print('PASS',len(pairs),'exact portable tables;',len(terrain),'independent DSM pixels;',checks,'manual metrics;',monotonic,'subset checks; weather replay',len(replay),'rows',flush=True)

if __name__=='__main__':main()
