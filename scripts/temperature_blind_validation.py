"""미사용 목표결빙4의 예측 봉인·수집·일회 평가로 온도 개선을 검증한다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.point_inputs import PointInputBuilder
from src.temperature_transfer import WEATHER_FEATURES, validate_development
from src.thermal_ice import fixed_thermal_rule, diagnostic_report
from src.validation import regression_metrics
from scripts.fresh_station_validation import ensure_unopened, verify_seal, old_freezes, temperature_report
from scripts.resume_fresh_collection import main as collection_main
from scripts.download_kma_external_development import write_json

PRIVATE = ROOT / 'outputs/private'
SOURCE = PRIVATE / 'releases/20261007/outputs/private'
DEFAULT = PRIVATE / 'temperature_blind_20261010_v1'
PLAN = ROOT / 'config/temperature_blind_validation_20261010.json'


def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))


def write(p, value):
    json.dumps(value, allow_nan=False)
    if Path(p).exists(): raise FileExistsError('Preserve existing evidence: ' + str(p))
    write_json(Path(p), value)


def prepare(out):
    if out.exists(): raise FileExistsError('Preserve existing blind version')
    original, reserved = old_freezes()
    plan = read(PLAN); ids = set().union(*map(set, plan['station_groups'].values()))
    ensure_unopened(PRIVATE, ids)
    if len(ids) != 4 or ids & set(plan['competition_stations_excluded_from_external_requests']):
        raise ValueError('Only four unopened target stations permitted')
    development = PRIVATE / 'temperature_loss_20261010_v1'
    review = read(development / 'summary.json')
    if read(development / 'independent_verification.json')['status'] != 'independent_temperature_audit_passed':
        raise ValueError('Development audit required')
    for r in review['files']:
        if sha(development / r) != review['files'][r]: raise ValueError('Development evidence changed')
    data_path = development / 'development_inputs.parquet'
    data = pd.read_parquet(data_path); validate_development(data)
    if len(set(data.station)) != 23 or ids & set(data.station): raise ValueError('New targets in training')
    config_path = ROOT / 'config/temperature_loss_experiment.json'
    config = read(config_path)
    cat_path = SOURCE / 'external/kma_rwis_reference/station_catalog.csv'
    cat = pd.read_csv(cat_path, dtype={'station': str}).set_index('station')
    if not cat.loc[sorted(ids), 'station_type'].eq('목표(결빙)').all(): raise ValueError('Expected icing targets')
    ice_dir = SOURCE / 'external_augmentation_nested_v1/baseline'
    info = read(ice_dir / 'fit_manifest.json')
    if sha(ice_dir / 'model.joblib') != info['files']['model.joblib']: raise ValueError('Original Ice model changed')
    out.mkdir(parents=True); shutil.copy2(PLAN, out / 'plan.json'); shutil.copy2(__file__, out / 'analysis_source.py')
    paths = [data_path, config_path, cat_path, PLAN, Path(__file__), ice_dir / 'model.joblib', ice_dir / 'fit_manifest.json',
             SOURCE / 'sensor_availability/metadata.csv', *(SOURCE / 'point_sources').glob('*')]
    paths += [ROOT / rel for rel in ['src/point_inputs.py', 'src/weather_features.py', 'src/thermal_ice.py',
                                    'src/kma_rwis_download.py', 'src/kma_rwis_transport.py', 'scripts/resume_fresh_collection.py']]
    write(out / 'input_signature.json', {str(i): {'path': str(p), 'sha256': sha(p)} for i, p in enumerate(paths) if p.is_file()})
    cutoff = pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1)
    aws = pd.read_parquet(SOURCE / 'point_sources/aws.parquet'); asos = pd.read_parquet(SOURCE / 'point_sources/asos.parquet')
    rwis = pd.read_parquet(SOURCE / 'point_sources/rwis.parquet')
    meta = pd.read_csv(SOURCE / 'sensor_availability/metadata.csv', dtype={'station': str})
    meta = meta.loc[meta.kind.eq('RWIS'), ['station', 'route', 'lat', 'lon']]
    builder = PointInputBuilder(aws.loc[aws.source_time.lt(cutoff)], asos.loc[asos.source_time.lt(cutoff)], rwis.loc[rwis.time.lt(cutoff)],
                              pd.read_csv(SOURCE / 'point_sources/weather_coordinates.csv', dtype={'station_id': str}), meta)
    mask = np.isfinite(data.road_temp) & np.isfinite(data.asos_air_temp)
    models = {}; receipts = []
    with threadpool_limits(limits=2):
        for iterations in [100, 300]:
            parameters = config['hgb_parameters'] | {'loss': 'squared_error', 'max_iter': iterations}
            model = HistGradientBoostingRegressor(**parameters)
            model.fit(data.loc[mask, WEATHER_FEATURES], data.loc[mask, 'road_temp'])
            name = f'weather_hgb{iterations}'; joblib.dump(model, out / (name + '.joblib'), compress=3)
            models[name] = model
            receipts.append({'name': name, 'training_rows': int(mask.sum()), 'training_stations': sorted(data.loc[mask, 'station'].unique()),
                             'parameters': parameters, 'features': WEATHER_FEATURES, 'model_sha256': sha(out / (name + '.joblib'))})
    write(out / 'fit_receipts.json', receipts)
    parts = []; references = []; points = []
    times = pd.date_range(plan['development_start_kst'], cutoff, freq='10min', inclusive='left')
    ice_model = joblib.load(ice_dir / 'model.joblib')
    for group, stations in plan['station_groups'].items():
        for station in stations:
            point = {k: cat.loc[station, k] for k in ['route', 'lat', 'lon', 'elevation_m']}; point['station'] = station
            point['route'] = {'통영-대전중부': '통영-대전중부선'}.get(point['route'], point['route'])
            x, refs = builder.build(point, times); x['elevation_m'] = point['elevation_m']
            if {'ice', 'state_raw', 'road_temp'} & set(x): raise ValueError('Target measurement in point inputs')
            x.to_parquet(out / f'inputs_{station}.parquet', index=False, compression='zstd')
            q = x[['station', 'time']].copy(); q['group'] = group
            with threadpool_limits(limits=2):
                score = ice_model.predict_proba(x[info['features']])[:, 1]
                q['original_ice'] = (score >= info['threshold']).astype(int)
                q['original_ice_score'] = score; q['original_threshold'] = info['threshold']
                for name, model in models.items():
                    t = np.where(x.asos_air_temp.notna(), model.predict(x[WEATHER_FEATURES]), np.nan)
                    q[name] = t
                    q['thermal_hgb' + name[-3:]], _, _ = fixed_thermal_rule(t, x, q.original_ice.to_numpy(), require_moisture=True)
            parts.append(q); points.append(point); references.append({'station': station, 'references': refs})
    pd.DataFrame(points).to_csv(out / 'points.csv', index=False, encoding='utf-8-sig')
    write(out / 'point_references.json', references)
    predictions = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    if len(predictions) != len(times) * 4 or predictions.duplicated(['station', 'time']).any(): raise ValueError('Incomplete new target grid')
    predictions.to_parquet(out / 'predictions.parquet', index=False, compression='zstd')
    write(out / 'prediction_seal.json', {'status': 'fresh_station_predictions_frozen_before_requests',
        'sealed_at_utc': datetime.now(timezone.utc).isoformat(), 'new_outcomes_present_at_seal': False,
        'rows': len(predictions), 'stations': sorted(ids), 'original_frozen_files': original, 'reserved_frozen_files': reserved,
        'files': {p.relative_to(out).as_posix(): sha(p) for p in out.iterdir() if p.is_file()}})
    verify_seal(out); print('New four-station predictions sealed:', len(predictions), flush=True)


def audit(out):
    seal = verify_seal(out)
    if (out / 'download_manifest.json').exists(): raise ValueError('Audit before outcomes required')
    ensure_unopened(PRIVATE, seal['stations'])
    q = pd.read_parquet(out / 'predictions.parquet')
    expected = pd.date_range('2024-11-01', '2025-02-28 23:50', freq='10min')
    with threadpool_limits(limits=2):
        for receipt in read(out / 'fit_receipts.json'):
            model = joblib.load(out / (receipt['name'] + '.joblib'))
            if sha(out / (receipt['name'] + '.joblib')) != receipt['model_sha256']: raise ValueError('Model changed')
            for station, part in q.groupby('station'):
                if not pd.DatetimeIndex(part.time).equals(expected): raise ValueError('Missing planned slots')
                x = pd.read_parquet(out / f'inputs_{station}.parquet')
                if not part[['station', 'time']].reset_index(drop=True).equals(x[['station', 'time']].reset_index(drop=True)):
                    raise ValueError('Point row order differs')
                p = np.where(x.asos_air_temp.notna(), model.predict(x[receipt['features']]), np.nan)
                np.testing.assert_allclose(p, part[receipt['name']], rtol=0, atol=0, equal_nan=True)
                ruled, _, _ = fixed_thermal_rule(p, x, part.original_ice.to_numpy(), require_moisture=True)
                np.testing.assert_array_equal(ruled, part['thermal_hgb' + receipt['name'][-3:]])
    write(out / 'prediction_audit.json', {'status': 'passed', 'new_outcomes_present': False,
        'audited_at_utc': datetime.now(timezone.utc).isoformat(), 'seal_sha256': sha(out / 'prediction_seal.json'),
        'prediction_values_checked': len(q) * 2, 'stations': seal['stations']})
    print('Pre-request prediction audit passed', flush=True)


def collect(out, credentials):
    seal = verify_seal(out)
    if not (out / 'download_manifest.json').exists():
        first = datetime.now(timezone.utc).isoformat()
        if first <= seal['sealed_at_utc']: raise ValueError('Request starts before seal')
        write(out / 'download_manifest.json', {'first_request_utc': first, 'records': {}})
    (out / 'observations').mkdir(exist_ok=True)
    sys.argv = ['resume_fresh_collection.py', '--experiment', str(out), '--workers', '3']
    if credentials is not None: sys.argv.extend(['--credentials-file', str(credentials)])
    collection_main()


def evaluate(out):
    verify_seal(out)
    if (out / 'summary.json').exists(): raise FileExistsError('Preserve once-opened evaluation')
    manifest = read(out / 'download_manifest.json')
    if manifest.get('status') != 'complete' or len(manifest['records']) != 480: raise ValueError('Full four-station collection required')
    frames = []
    for name, r in manifest['records'].items():
        path = out / 'observations' / (name + '.parquet')
        if sha(path) != r['sha256']: raise ValueError('Observation signature changed')
        frames.append(pd.read_parquet(path))
    observed = pd.concat(frames, ignore_index=True)
    if observed.duplicated(['station', 'time']).any(): raise ValueError('Duplicate raw observations')
    q = pd.read_parquet(out / 'predictions.parquet')
    frame = q.merge(observed[['station', 'time', 'road_temp', 'ice', 'state_raw', 'lat', 'lon']],
                    on=['station', 'time'], how='left', validate='one_to_one', indicator=True)
    if len(frame) != len(q): raise ValueError('Evaluation population changed')
    frame.to_parquet(out / 'evaluation.parquet', index=False, compression='zstd')
    plan = read(out / 'plan.json')
    finite = np.isfinite(frame.road_temp) & np.isfinite(frame.weather_hgb100) & np.isfinite(frame.weather_hgb300)
    temperature = {name: temperature_report(frame, frame[name]) for name in plan['temperature_comparison']}
    near = {name: temperature_report(frame.loc[finite & frame.road_temp.between(-2, 2)], frame.loc[finite & frame.road_temp.between(-2, 2), name])
            for name in plan['temperature_comparison']}
    for name in plan['temperature_comparison']:
        if temperature[name]['pooled']['n'] != int(finite.sum()): raise ValueError('Temperature domains differ')
        independent = regression_metrics(frame.loc[finite, 'road_temp'], frame.loc[finite, name])
        for k in ['mae', 'rmse', 'bias']: np.testing.assert_allclose(independent[k], temperature[name]['pooled'][k], rtol=0, atol=1e-10)
    ice_metrics = {}; station_frames = []
    for name in plan['frozen_ice_policies']:
        metrics, stations, days, events = diagnostic_report(frame, frame[name]); ice_metrics[name] = metrics
        stations['policy'] = name; station_frames.append(stations)
        days.to_csv(out / (name + '_daily.csv'), index=False); events.to_csv(out / (name + '_events.csv'), index=False)
    pd.concat(station_frames).to_csv(out / 'ice_station_metrics.csv', index=False, encoding='utf-8-sig')
    coverage = [{'station': str(st), 'planned_rows': len(p), 'received_rows': int(p._merge.eq('both').sum()),
                 'defined_state_rows': int(p.ice.isin([0, 1]).sum()), 'ice_rows': int(p.ice.eq(1).sum())} for st, p in frame.groupby('station')]
    b = temperature['weather_hgb100']; c = temperature['weather_hgb300']
    improved = all(c['station_macro'][k] < b['station_macro'][k] for k in ['mae', 'rmse'])
    safe = all(c['stations'][s]['mae'] <= b['stations'][s]['mae'] * 1.05 for s in b['stations'] if b['stations'][s]['n'])
    old_freezes()
    write(out / 'summary.json', {'status': 'new_four_station_once_opened_evaluation_complete', 'evaluated_at_utc': datetime.now(timezone.utc).isoformat(),
        'temperature': temperature, 'near_freezing': near, 'ice_metrics': ice_metrics, 'coverage': coverage,
        'temperature_primary_gate_passed': improved and safe, 'no_retuning_permitted': True,
        'scope': plan['claim_limits'], 'seal_sha256': sha(out / 'prediction_seal.json'),
        'evaluation_sha256': sha(out / 'evaluation.parquet'), 'protected_or_future_outcomes_used': False})
    print(json.dumps(read(out / 'summary.json'), ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('phase', choices=['prepare', 'audit', 'collect', 'evaluate'])
    parser.add_argument('--output', type=Path, default=DEFAULT); parser.add_argument('--credentials-file', type=Path)
    args = parser.parse_args(); out = args.output.resolve()
    if not out.is_relative_to(PRIVATE.resolve()): raise ValueError('Private output required')
    if args.phase == 'prepare': prepare(out)
    elif args.phase == 'audit': audit(out)
    elif args.phase == 'collect': collect(out, args.credentials_file)
    else: evaluate(out)


if __name__ == '__main__': main()
