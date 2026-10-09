"""인계 폴더만으로 회귀 재적합·고정 추론·새 지점 지표를 재현한다. 네트워크 없음."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import sys
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.research_delivery import verify_delivery, verify_cohort, file_sha
from scripts.audit_joint_surface import report, close


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args(); root = args.delivery.resolve()
    manifest = verify_delivery(root)
    if args.verify_only:
        print('Delivery hashes verified:', len(manifest['files'])); return
    destination = root / 'reproduction_receipt.json'
    if destination.exists():
        raise FileExistsError('Preserve completed reproduction; use --verify-only')
    fresh = root / 'fresh_validation'; plan = read(fresh / 'plan.json'); fit = read(fresh / 'fit_receipt.json')
    train = pd.read_parquet(root / 'training/temperature_first_winter23.parquet')
    query = pd.read_parquet(fresh / 'predictions.parquet'); evaluation = pd.read_parquet(fresh / 'evaluation.parquet')
    verify_cohort(train, query, plan['station_groups'])
    pd.testing.assert_frame_equal(query, evaluation[query.columns])
    features = fit['features']; mask = np.isfinite(train.road_temp) & train.asos_air_temp.notna()
    assert int(mask.sum()) == fit['training_rows']
    clone = HistGradientBoostingRegressor(**fit['parameters'])
    saved = joblib.load(fresh / 'weather_hgb23.joblib')
    ice = joblib.load(root / 'models/original_ice.joblib'); ridge = joblib.load(root / 'models/original_weather_ridge.joblib')
    ice_info = read(root / 'models/original_ice_fit.json')
    with threadpool_limits(limits=2):
        clone.fit(train.loc[mask, features], train.loc[mask, 'road_temp'])
        for station in sorted(query.station.unique()):
            q = query[query.station.eq(station)].reset_index(drop=True)
            x = pd.read_parquet(fresh / ('inputs_' + station + '.parquet'))
            assert not {'road_temp', 'ice', 'state_raw'} & set(x)
            pd.testing.assert_frame_equal(q[['station', 'time']], x[['station', 'time']])
            t = np.where(x.asos_air_temp.notna(), clone.predict(x[features]), np.nan)
            original_t = np.where(x.asos_air_temp.notna(), ridge.predict(x[features]), np.nan)
            np.testing.assert_allclose(t, np.where(x.asos_air_temp.notna(), saved.predict(x[features]), np.nan), rtol=0, atol=0, equal_nan=True)
            np.testing.assert_allclose(q.weather_hgb23, t, rtol=0, atol=0, equal_nan=True)
            np.testing.assert_allclose(q.original_weather_ridge, original_t, rtol=0, atol=0, equal_nan=True)
            score = ice.predict_proba(x[ice_info['features']])[:, 1]
            np.testing.assert_allclose(q.original_ice_score, score, rtol=0, atol=0)
            original = (score >= ice_info['threshold']).astype(int)
            np.testing.assert_array_equal(q.original_ice, original)
            wet = (x.aws_dewpoint.to_numpy() >= t) | (x.rain15_max_3h.to_numpy() > 0) | (x.asos_snow_cm.to_numpy() > 0)
            fallback = ~np.isfinite(t) | x[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].isna().all(axis=1).to_numpy()
            np.testing.assert_array_equal(q.thermal_moisture, np.where(fallback, original, (t <= 0) & wet).astype(int))
    summary = read(fresh / 'summary.json')
    for policy in plan['frozen_policies']:
        result, _ = report(evaluation, evaluation[policy])
        for key, value in result.items():
            close(value, summary['metrics'][policy][key])
    for policy in plan['temperature_comparison']:
        valid = np.isfinite(evaluation.road_temp) & np.isfinite(evaluation[policy]); actual_stations = {}
        for station in sorted(evaluation.station.unique()):
            part = evaluation[valid & evaluation.station.eq(station)]
            error = (part[policy] - part.road_temp).to_numpy()
            expected = summary['temperature'][policy]['stations'][station]
            actual = dict(n=len(error), mae=float(np.abs(error).mean()) if len(error) else None,
                          rmse=float(np.sqrt((error * error).mean())) if len(error) else None,
                          bias=float(error.mean()) if len(error) else None)
            for key, value in actual.items(): close(value, expected[key])
            actual_stations[station] = actual
        active = [row for row in actual_stations.values() if row['n']]
        for key in ['mae', 'rmse', 'bias']:
            close(float(np.mean([row[key] for row in active])) if active else None, summary['temperature'][policy]['station_macro'][key])
    receipt = dict(status='passed', checked_at_utc=datetime.now(timezone.utc).isoformat(),
                   manifest_sha256=file_sha(root / 'manifest.json'), hashed_files=len(manifest['files']),
                   first_winter_temperature_refit_exact=True, fixed_query_rows=len(query), new_blind_test=False,
                   metrics_reproduced=True, network_requests=0, full_spatial_source_pipeline_replayed=False)
    destination.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
