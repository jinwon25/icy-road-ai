"""개발에서 고정한 평균 후보를 미사용 호남2곳에 봉인한 뒤 한 번 평가한다."""
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
from src.evidence_review import review_domain
from src.point_inputs import PointInputBuilder
from src.temperature_transfer import WEATHER_FEATURES
from src.weather_distance_ablation import DISTANCE_FREE_FEATURES
from src.temperature_mean import equal_mean
from src.thermal_ice import fixed_thermal_rule, diagnostic_report
from scripts.fresh_station_validation import ensure_unopened, verify_seal, old_freezes, temperature_report
from scripts.resume_fresh_collection import main as collection_main

PRIVATE = ROOT / 'outputs/private'
SOURCE = PRIVATE / 'releases/20261007/outputs/private'
DEFAULT = PRIVATE / 'temperature_mean_blind_20261010_v1'
PLAN = ROOT / 'config/temperature_mean_blind_validation_20261010.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False); handle.write('\n')


def prepare(out):
    if out.exists():
        raise FileExistsError('Preserve existing blind version')
    freezes = old_freezes(); plan = read(PLAN)
    ids = set().union(*map(set, plan['station_groups'].values()))
    ensure_unopened(PRIVATE, ids)
    if ids != {'23102', '23407'} or ids & set(plan['competition_stations_excluded_from_external_requests']):
        raise ValueError('Only the two metadata-selected unopened stations permitted')
    development = PRIVATE / 'temperature_mean_20261010_v1'
    summary, audit = read(development / 'summary.json'), read(development / 'independent_verification.json')
    if not summary['development_overall_temperature_gate_passed'] or audit['status'] != 'independent_equal_mean_audit_passed' or sha(development / 'summary.json') != audit['summary_sha256']:
        raise ValueError('Audited development gate must pass before new validation')
    data_path = PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet'
    data = review_domain(pd.read_parquet(data_path))
    if len(set(data.station)) != 23 or ids & set(data.station):
        raise ValueError('New target in training')
    design = PRIVATE / 'temperature_mean_validation_design_20261010_v1/design_receipt.json'
    if set(read(design)['selected_stations']) != ids or read(design)['outcomes_read'] is not False:
        raise ValueError('Metadata-only design required')
    cat_path = SOURCE / 'external/kma_rwis_reference/station_catalog.csv'
    cat = pd.read_csv(cat_path, dtype={'station': str}).set_index('station')
    if not cat.loc[sorted(ids), 'route'].eq('호남선').all():
        raise ValueError('Expected Honam validation domain')
    base = PRIVATE / 'temperature_blind_20261010_v1'
    verify_seal(base)
    base_fit = next(r for r in read(base / 'fit_receipts.json') if r['name'] == 'weather_hgb100')
    parameters = read(ROOT / 'config/weather_distance_experiment.json')['hgb_parameters']
    mask = np.isfinite(data.road_temp) & np.isfinite(data.asos_air_temp)
    if base_fit['training_rows'] != int(mask.sum()) or set(base_fit['training_stations']) != set(data.station):
        raise ValueError('Reused baseline fitting scope differs')
    model14 = joblib.load(base / 'weather_hgb100.joblib')
    if any(model14.get_params().get(k) != v for k, v in parameters.items()) or base_fit['model_sha256'] != sha(base / 'weather_hgb100.joblib'):
        raise ValueError('Reused baseline model differs')
    pd.testing.assert_frame_equal(data, pd.read_parquet(PRIVATE / 'temperature_loss_20261010_v1/development_inputs.parquet'))
    ice_dir = SOURCE / 'external_augmentation_nested_v1/baseline'; ice_info = read(ice_dir / 'fit_manifest.json')
    if sha(ice_dir / 'model.joblib') != ice_info['files']['model.joblib']:
        raise ValueError('Original fallback model changed')
    out.mkdir(); shutil.copy2(PLAN, out / 'plan.json'); shutil.copy2(__file__, out / 'analysis_source.py')
    shutil.copy2(base / 'weather_hgb100.joblib', out / 'weather14.joblib')
    paths = [data_path, PLAN, Path(__file__), design, cat_path, base / 'weather_hgb100.joblib', base / 'fit_receipts.json',
             development / 'summary.json', development / 'independent_verification.json', ice_dir / 'model.joblib', ice_dir / 'fit_manifest.json',
             ROOT / 'config/weather_distance_experiment.json', SOURCE / 'sensor_availability/metadata.csv', *(SOURCE / 'point_sources').glob('*')]
    paths += [ROOT / rel for rel in ['src/point_inputs.py', 'src/weather_features.py', 'src/thermal_ice.py', 'src/temperature_mean.py',
                                    'src/kma_rwis_download.py', 'src/kma_rwis_transport.py', 'scripts/resume_fresh_collection.py']]
    write(out / 'input_signature.json', {str(i): {'path': str(p), 'sha256': sha(p)} for i, p in enumerate(paths) if p.is_file()})
    with threadpool_limits(limits=2):
        model12 = HistGradientBoostingRegressor(**parameters).fit(data.loc[mask, list(DISTANCE_FREE_FEATURES)], data.loc[mask, 'road_temp'])
    joblib.dump(model12, out / 'weather12.joblib', compress=3)
    receipts = []
    for name, model, columns, reused in [('weather14', model14, WEATHER_FEATURES, True), ('weather12', model12, list(DISTANCE_FREE_FEATURES), False)]:
        receipts.append(dict(name=name, training_rows=int(mask.sum()), training_stations=sorted(data.station.unique()),
                             parameters=parameters, features=columns, model_sha256=sha(out / (name+'.joblib')), reused=reused))
    write(out / 'fit_receipts.json', receipts)
    cutoff = pd.Timestamp('2025-03-01')
    aws = pd.read_parquet(SOURCE / 'point_sources/aws.parquet'); asos = pd.read_parquet(SOURCE / 'point_sources/asos.parquet')
    rwis = pd.read_parquet(SOURCE / 'point_sources/rwis.parquet')
    meta = pd.read_csv(SOURCE / 'sensor_availability/metadata.csv', dtype={'station': str})
    builder = PointInputBuilder(aws.loc[aws.source_time.lt(cutoff)], asos.loc[asos.source_time.lt(cutoff)], rwis.loc[rwis.time.lt(cutoff)],
                               pd.read_csv(SOURCE / 'point_sources/weather_coordinates.csv', dtype={'station_id': str}),
                               meta.loc[meta.kind.eq('RWIS'), ['station', 'route', 'lat', 'lon']])
    times = pd.date_range('2024-11-01', cutoff, freq='10min', inclusive='left')
    ice_model = joblib.load(ice_dir / 'model.joblib'); parts, points, refs = [], [], []
    for group, stations in plan['station_groups'].items():
        for station in stations:
            point = {k: cat.loc[station, k] for k in ['route', 'lat', 'lon', 'elevation_m']}; point['station'] = station
            x, selected = builder.build(point, times); x['elevation_m'] = point['elevation_m']
            if {'ice', 'state_raw', 'road_temp'} & set(x):
                raise ValueError('Target outcome in inference inputs')
            x.to_parquet(out / f'inputs_{station}.parquet', index=False, compression='zstd')
            q = x[['station', 'time']].copy(); q['group'] = group
            with threadpool_limits(limits=2):
                score = ice_model.predict_proba(x[ice_info['features']])[:, 1]
                q['original_ice_score'] = score; q['original_ice'] = (score >= ice_info['threshold']).astype(int)
                q['weather14'] = np.where(x.asos_air_temp.notna(), model14.predict(x[WEATHER_FEATURES]), np.nan)
                q['weather12'] = np.where(x.asos_air_temp.notna(), model12.predict(x[list(DISTANCE_FREE_FEATURES)]), np.nan)
            q['equal_mean'] = equal_mean(q.weather14, q.weather12)
            for name in ['weather14', 'equal_mean']:
                q['thermal_'+name], _, _ = fixed_thermal_rule(q[name], x, q.original_ice, require_moisture=True)
            parts.append(q); points.append(point); refs.append(dict(station=station, references=selected))
    pd.DataFrame(points).to_csv(out / 'points.csv', index=False, encoding='utf-8-sig'); write(out / 'point_references.json', refs)
    q = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    if len(q) != len(times)*2 or q.duplicated(['station', 'time']).any():
        raise ValueError('Incomplete planned grid')
    q.to_parquet(out / 'predictions.parquet', index=False, compression='zstd')
    write(out / 'prediction_seal.json', dict(status='fresh_station_predictions_frozen_before_requests', sealed_at_utc=datetime.now(timezone.utc).isoformat(),
          new_outcomes_present_at_seal=False, rows=len(q), stations=sorted(ids), original_frozen_files=freezes[0], reserved_frozen_files=freezes[1],
          files={p.relative_to(out).as_posix(): sha(p) for p in out.iterdir() if p.is_file()}))
    verify_seal(out); print('Two-station mean predictions sealed:', len(q), flush=True)


def audit(out):
    seal = verify_seal(out)
    if (out / 'download_manifest.json').exists():
        raise ValueError('Pre-outcome audit required')
    ensure_unopened(PRIVATE, seal['stations'])
    q = pd.read_parquet(out / 'predictions.parquet')
    data = pd.read_parquet(PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet')
    mask = np.isfinite(data.road_temp) & np.isfinite(data.asos_air_temp)
    verified = 0
    with threadpool_limits(limits=2):
        for record in read(out / 'fit_receipts.json'):
            refit = HistGradientBoostingRegressor(**record['parameters']).fit(data.loc[mask, record['features']], data.loc[mask, 'road_temp'])
            model = joblib.load(out / (record['name']+'.joblib'))
            if sha(out / (record['name']+'.joblib')) != record['model_sha256']:
                raise ValueError('Model changed')
            for station, part in q.groupby('station'):
                x = pd.read_parquet(out / f'inputs_{station}.parquet')
                if not part[['station', 'time']].reset_index(drop=True).equals(x[['station', 'time']].reset_index(drop=True)):
                    raise ValueError('Input alignment differs')
                expected = np.where(x.asos_air_temp.notna(), refit.predict(x[record['features']]), np.nan)
                actual = np.where(x.asos_air_temp.notna(), model.predict(x[record['features']]), np.nan)
                np.testing.assert_allclose(actual, expected, rtol=0, atol=0, equal_nan=True)
                np.testing.assert_allclose(part[record['name']], expected, rtol=0, atol=0, equal_nan=True); verified += len(part)
        ice_dir = SOURCE / 'external_augmentation_nested_v1/baseline'; info = read(ice_dir / 'fit_manifest.json')
        model = joblib.load(ice_dir / 'model.joblib')
        for station, part in q.groupby('station'):
            x = pd.read_parquet(out / f'inputs_{station}.parquet')
            np.testing.assert_allclose(part.equal_mean, (part.weather14+part.weather12)/2, rtol=0, atol=1e-12, equal_nan=True)
            p = model.predict_proba(x[info['features']])[:, 1]
            np.testing.assert_allclose(part.original_ice_score, p, rtol=0, atol=0)
            np.testing.assert_array_equal(part.original_ice, p >= info['threshold'])
            for name in ['weather14', 'equal_mean']:
                t = part[name].to_numpy(); water = x[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
                fallback = ~np.isfinite(t) | np.isnan(water).all(axis=1)
                ruled = ((t <= 0) & ((water[:, 0] >= t) | (water[:, 1] > 0) | (water[:, 2] > 0))).astype(int)
                ruled[fallback] = part.original_ice.to_numpy()[fallback]
                np.testing.assert_array_equal(part['thermal_'+name], ruled)
    write(out / 'prediction_audit.json', dict(status='passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
          seal_sha256=sha(out / 'prediction_seal.json'), independent_training_refits=2, prediction_values_checked=verified,
          mean_values_checked=len(q), original_ice_scores_checked=len(q), new_outcomes_present=False))
    print('Pre-request mean prediction and refitting audit passed', flush=True)


def collect(out, credentials):
    seal = verify_seal(out)
    if read(out / 'prediction_audit.json')['status'] != 'passed':
        raise ValueError('Prediction audit required')
    if not (out / 'download_manifest.json').exists():
        first = datetime.now(timezone.utc).isoformat()
        if first <= seal['sealed_at_utc']:
            raise ValueError('Request before prediction seal')
        write(out / 'download_manifest.json', dict(first_request_utc=first, records={}))
    (out / 'observations').mkdir(exist_ok=True)
    sys.argv = ['resume_fresh_collection.py', '--experiment', str(out), '--workers', '3']
    if credentials is not None:
        sys.argv.extend(['--credentials-file', str(credentials)])
    collection_main()


def evaluate(out):
    verify_seal(out)
    if (out / 'summary.json').exists():
        raise FileExistsError('Preserve once-opened evaluation')
    manifest = read(out / 'download_manifest.json')
    if manifest.get('status') != 'complete' or len(manifest['records']) != 240:
        raise ValueError('Full two-station collection required')
    observed = []
    for name, record in manifest['records'].items():
        p = out / 'observations' / (name+'.parquet')
        if sha(p) != record['sha256']:
            raise ValueError('Observation changed')
        observed.append(pd.read_parquet(p))
    observed = pd.concat(observed, ignore_index=True)
    q = pd.read_parquet(out / 'predictions.parquet')
    frame = q.merge(observed[['station', 'time', 'road_temp', 'ice', 'state_raw', 'lat', 'lon']], on=['station', 'time'], how='left', validate='one_to_one', indicator=True)
    frame.to_parquet(out / 'evaluation.parquet', index=False, compression='zstd')
    finite = np.isfinite(frame.road_temp) & np.isfinite(frame.weather14) & np.isfinite(frame.equal_mean)
    temperature = {n: temperature_report(frame, frame[n]) for n in ['weather14', 'equal_mean']}
    near = {n: temperature_report(frame.loc[finite & frame.road_temp.between(-2, 2)], frame.loc[finite & frame.road_temp.between(-2, 2), n]) for n in temperature}
    assert all(report['pooled']['n'] == int(finite.sum()) for report in temperature.values())
    ice = {}
    for n in read(out / 'plan.json')['frozen_ice_policies']:
        report, stations, days, events = diagnostic_report(frame, frame[n]); ice[n] = report
        for suffix, values in [('stations', stations), ('days', days), ('events', events)]:
            values.to_csv(out / f'{n}_{suffix}.csv', index=False, encoding='utf-8-sig')
    b, c = temperature['weather14'], temperature['equal_mean']
    complete_stations = all(values['n'] > 0 for values in b['stations'].values())
    temp_gate = complete_stations and all(c['station_macro'][k] < b['station_macro'][k] for k in ['mae', 'rmse'])
    temp_gate &= all(c['stations'][s]['mae'] <= r['mae']*1.05 for s, r in b['stations'].items() if r['n'])
    near_ok = near['weather14']['pooled']['n'] > 0 and near['equal_mean']['pooled']['mae'] <= near['weather14']['pooled']['mae']
    coverage = [dict(station=s, planned_rows=len(p), received_rows=int(p._merge.eq('both').sum()), valid_temperature=int((np.isfinite(p.road_temp)&np.isfinite(p.equal_mean)).sum()),
                     defined_state_rows=int(p.ice.isin([0, 1]).sum()), ice_rows=int(p.ice.eq(1).sum())) for s, p in frame.groupby('station')]
    old_freezes()
    write(out / 'summary.json', dict(status='new_two_honam_once_opened_evaluation_complete', evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
          temperature=temperature, near_freezing=near, ice_metrics=ice, coverage=coverage,
          temperature_primary_gate_passed=bool(temp_gate and near_ok), no_retuning_permitted=True, candidate_promoted=False,
          seal_sha256=sha(out / 'prediction_seal.json'), evaluation_sha256=sha(out / 'evaluation.parquet'),
          protected_or_future_outcomes_used=False, scope=read(out / 'plan.json')['claim_limits']))
    print(json.dumps(read(out / 'summary.json'), ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('phase', choices=['prepare', 'audit', 'collect', 'evaluate'])
    parser.add_argument('--output', type=Path, default=DEFAULT); parser.add_argument('--credentials-file', type=Path)
    args = parser.parse_args(); out = args.output.resolve()
    if not out.is_relative_to(PRIVATE.resolve()):
        raise ValueError('Private output required')
    if args.phase == 'prepare': prepare(out)
    elif args.phase == 'audit': audit(out)
    elif args.phase == 'collect': collect(out, args.credentials_file)
    else: evaluate(out)


if __name__ == '__main__':
    main()
