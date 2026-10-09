"""미사용 지점의 예측을 먼저 봉인하고 수집·일회 평가를 분리한다."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, shutil, sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.point_inputs import PointInputBuilder
from src.thermal_ice import fixed_thermal_rule, diagnostic_report, validate_development
from src.kma_rwis_download import daily_requests, load_auth_key, parse_observations, exact_ten_minute_grid
from src.kma_rwis_transport import ValidatedRoadClient
from src.external_reserved import verify_reserved_freeze
from src.frozen_assessment import verify_freeze
from scripts.baseline_ice_logistic import FEATURES
from scripts.reproduce_weather_fallback import PARAMS
from scripts.download_kma_external_development import write_json

PRIVATE = ROOT / 'outputs/private'
RELEASE = PRIVATE / 'releases/20261007'
SOURCE = RELEASE / 'outputs/private'
DEFAULT_OUT = PRIVATE / 'fresh_station_validation_20261009_v2'
PLAN = ROOT / 'config/fresh_station_validation.json'


def read(p): return json.loads(Path(p).read_text('utf-8'))
def write(p, value):
    json.dumps(value, allow_nan=False)
    write_json(Path(p), value)


def old_freezes():
    return len(verify_freeze(RELEASE)['files']), len(verify_reserved_freeze(RELEASE, SOURCE / 'external_reserved_predictions_v1')['files'])


def ensure_unopened(private,stations):
    """정답 요청 기록이 있는 같은 지점에 새 블라인드 봉인을 만들지 않는다."""
    wanted=set(stations)
    for path in Path(private).rglob('download_manifest.json'):
        records=read(path).get('records',{})
        if any(str(row.get('station')) in wanted for row in records.values()):
            raise ValueError('These station outcomes have already been requested; no new blind sealing')


def temperature_report(frame,prediction):
    """관측 공백 지점을 숨기지 않고 n=0·미정의 오차로 보존한다."""
    values=np.asarray(prediction,dtype=float);valid=np.isfinite(frame.road_temp)&np.isfinite(values)
    def regression(y,p):
        e=np.asarray(p)-np.asarray(y)
        if not len(e):return dict(n=0,mae=None,rmse=None,bias=None)
        return dict(n=len(e),mae=float(np.abs(e).mean()),rmse=float(np.sqrt((e*e).mean())),bias=float(e.mean()))
    stations={}
    for station in sorted(frame.station.unique()):
        mask=valid&frame.station.eq(station).to_numpy();stations[station]=regression(frame.road_temp.to_numpy()[mask],values[mask])
    active=[r for r in stations.values() if r['n']]
    return dict(pooled=regression(frame.road_temp.to_numpy()[valid],values[valid]),stations=stations,
                stations_with_valid_temperature=len(active),station_macro={k:float(np.mean([r[k] for r in active])) if active else None for k in ['mae','rmse','bias']})


def verify_seal(out):
    seal = read(out / 'prediction_seal.json')
    assert seal['new_outcomes_present_at_seal'] is False
    for name, checksum in seal['files'].items():
        assert sha(out / name) == checksum, 'Changed frozen prediction evidence'
    for entry in read(out / 'input_signature.json').values():
        assert sha(entry['path']) == entry['sha256'], 'Changed source input'
    return seal


def prepare(out):
    if out.exists(): raise FileExistsError('Preserve previous validation run')
    original_n, reserved_n = old_freezes()
    plan = read(PLAN); ids = {s for group in plan['station_groups'].values() for s in group}
    index_path = PRIVATE / 'ice_group_balanced_20261009_v1/development_index.parquet'
    raw_path = PRIVATE / 'ice_group_balanced_20261009_v1/feature_matrix.parquet'
    temp_path = PRIVATE / 'weather_fallback_20261009_v1/training_index.parquet'
    index = validate_development(pd.read_parquet(index_path)); raw = pd.read_parquet(raw_path); temp = pd.read_parquet(temp_path)
    pd.testing.assert_frame_equal(index[['station', 'time', 'group']], temp[['station', 'time', 'group']])
    assert not ids & set(index.station) and not ids & set(plan['competition_stations_excluded_from_external_requests'])
    assert len(ids) == 8 and len(set(index.station)) == 23
    ensure_unopened(PRIVATE,ids)
    # 재사용하는 14지점 비교 모델도 새 지점을 학습하지 않았는지 확인한다.
    ice_dir = SOURCE / 'external_augmentation_nested_v1/baseline'
    temp_dir = SOURCE / 'external_temperature_nested_v1/baseline'
    ice_info = read(ice_dir / 'fit_manifest.json'); temp_info = read(temp_dir / 'fit_manifest.json')
    assert sha(ice_dir / 'model.joblib') == ice_info['files']['model.joblib']
    assert sha(temp_dir / 'model.joblib') == temp_info['model_sha256']
    assert not ids & set(ice_info['training_stations']) and not ids & set(temp_info['training_stations'])
    out.mkdir(parents=True); shutil.copy2(PLAN, out / 'plan.json'); shutil.copy2(__file__, out / 'analysis_source.py')
    paths = [index_path, raw_path, temp_path, ice_dir / 'model.joblib', ice_dir / 'fit_manifest.json', temp_dir / 'model.joblib', temp_dir / 'fit_manifest.json',
             SOURCE / 'external/kma_rwis_reference/station_catalog.csv', SOURCE / 'sensor_availability/metadata.csv']
    paths += list((SOURCE / 'point_sources').glob('*'))
    for name in ['src/point_inputs.py', 'src/weather_features.py', 'src/thermal_ice.py', 'src/kma_rwis_download.py', 'src/kma_rwis_transport.py', 'scripts/baseline_ice_logistic.py']:
        paths.append(ROOT / name)
    signature = {str(n): dict(path=str(p), sha256=sha(p)) for n,p in enumerate(paths) if p.is_file()}
    write(out / 'input_signature.json', signature)
    catalog = pd.read_csv(SOURCE / 'external/kma_rwis_reference/station_catalog.csv', dtype={'station': str}).set_index('station')
    cutoff = pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1)
    point_source = SOURCE / 'point_sources'
    aws = pd.read_parquet(point_source / 'aws.parquet'); asos = pd.read_parquet(point_source / 'asos.parquet'); rwis = pd.read_parquet(point_source / 'rwis.parquet')
    meta = pd.read_csv(SOURCE / 'sensor_availability/metadata.csv', dtype={'station': str})
    meta = meta.loc[meta.kind.eq('RWIS'), ['station', 'route', 'lat', 'lon']]
    builder = PointInputBuilder(aws.loc[aws.source_time.lt(cutoff)], asos.loc[asos.source_time.lt(cutoff)], rwis.loc[rwis.time.lt(cutoff)],
                              pd.read_csv(point_source / 'weather_coordinates.csv', dtype={'station_id': str}), meta)
    times = pd.date_range(plan['development_start_kst'], cutoff, freq='10min', inclusive='left')
    mask = np.isfinite(temp.road_temp) & raw.asos_air_temp.notna()
    model = HistGradientBoostingRegressor(**PARAMS)
    with threadpool_limits(limits=2): model.fit(raw.loc[mask, FEATURES], temp.loc[mask, 'road_temp'])
    joblib.dump(model, out / 'weather_hgb23.joblib', compress=3)
    write(out / 'fit_receipt.json', dict(training_rows=int(mask.sum()), training_stations=sorted(set(index.loc[mask, 'station'])),
                                       parameters=PARAMS, features=FEATURES, model_sha256=sha(out / 'weather_hgb23.joblib'),
                                       training_identity=__import__('hashlib').sha256(pd.util.hash_pandas_object(temp.loc[mask, ['station','time','road_temp']], index=True).values.tobytes()).hexdigest()))
    ice_model = joblib.load(ice_dir / 'model.joblib'); ridge = joblib.load(temp_dir / 'model.joblib')
    parts, points, mapping = [], [], []
    for group, stations in plan['station_groups'].items():
        for station in stations:
            point = catalog.loc[station].to_dict(); point = {k: point[k] for k in ['route','lat','lon','elevation_m']}; point['station'] = station
            point['route'] = {'통영-대전중부': '통영-대전중부선'}.get(point['route'], point['route']); points.append(point)
            x, references = builder.build(point, times); x['elevation_m'] = point['elevation_m']
            assert not {'ice','state_raw','road_temp'} & set(x)
            x.to_parquet(out / f'inputs_{station}.parquet', index=False, compression='zstd')
            with threadpool_limits(limits=2):
                t = np.where(x.asos_air_temp.notna(), model.predict(x[FEATURES]), np.nan)
                original_t = np.where(x.asos_air_temp.notna(), ridge.predict(x[FEATURES]), np.nan)
                score = ice_model.predict_proba(x[ice_info['features']])[:, 1]
            original = (score >= ice_info['threshold']).astype(int)
            predicted, fallback, wet = fixed_thermal_rule(t, x, original, require_moisture=True)
            q = x[['station','time']].copy(); q['group'] = group; q['original_ice_score'] = score; q['original_threshold'] = ice_info['threshold']
            q['original_ice'] = original; q['thermal_moisture'] = predicted; q['fallback'] = fallback; q['moisture_evidence'] = wet
            q['original_weather_ridge'] = original_t; q['weather_hgb23'] = t; parts.append(q)
            mapping.append(dict(station=station, references=references, weather_valid_rows=int(np.isfinite(t).sum()),
                                aws_distance_km_min=float(x.aws_distance_km.min()), aws_distance_km_max=float(x.aws_distance_km.max()),
                                asos_distance_km=float(x.asos_distance_km.iloc[0])))
    pd.DataFrame(points).to_csv(out / 'points.csv', index=False, encoding='utf-8-sig'); write(out / 'point_references.json', mapping)
    q = pd.concat(parts).sort_values(['station','time']).reset_index(drop=True)
    assert len(q) == len(times)*8 and not q.duplicated(['station','time']).any()
    q.to_parquet(out / 'predictions.parquet', index=False, compression='zstd')
    write(out / 'prediction_seal.json', dict(status='fresh_station_predictions_frozen_before_requests', sealed_at_utc=datetime.now(timezone.utc).isoformat(),
                                            new_outcomes_present_at_seal=False, rows=len(q), stations=sorted(ids),
                                            original_frozen_files=original_n, reserved_frozen_files=reserved_n,
                                            files={p.relative_to(out).as_posix(): sha(p) for p in out.iterdir() if p.is_file()}))
    verify_seal(out); print('Sealed new station predictions:',len(q),flush=True)


def collect(out, credentials):
    seal = verify_seal(out); plan = read(out / 'plan.json'); manifest_path = out / 'download_manifest.json'
    audit = read(out / 'prediction_audit.json')
    assert audit['status'] == 'passed' and audit['new_outcomes_present'] is False
    assert audit['seal_sha256'] == sha(out / 'prediction_seal.json')
    manifest = read(manifest_path) if manifest_path.exists() else dict(first_request_utc=datetime.now(timezone.utc).isoformat(), records={})
    assert manifest['first_request_utc'] > seal['sealed_at_utc']
    write(manifest_path, manifest)
    client = ValidatedRoadClient(plan, load_auth_key(credentials), out / 'transport')
    jobs = list(daily_requests(plan, plan['development_start_kst'], plan['development_end_kst'], window_minutes=plan['window_minutes']))
    folder = out / 'observations'; folder.mkdir(exist_ok=True)
    for n,(station,start,end) in enumerate(jobs, 1):
        identifier = f'{station}_{start:%Y%m%d%H%M}'; path = folder / (identifier + '.parquet')
        if identifier in manifest['records']:
            assert path.exists() and sha(path) == manifest['records'][identifier]['sha256']; continue
        if path.exists(): raise ValueError('Unrecorded response evidence; preserve and inspect')
        body, transport = client.fetch(station, start, end)
        minute = parse_observations(body, station, start, end); frame = exact_ten_minute_grid(minute)
        frame.to_parquet(path, index=False, compression='zstd')
        manifest['records'][identifier] = dict(station=station, start_kst=start.isoformat(), end_kst=end.isoformat(), downloaded_at_utc=datetime.now(timezone.utc).isoformat(),
                                              sha256=sha(path), rows=len(frame), minute_rows=len(minute), transport=transport,
                                              invalid_timestamp_rows_excluded=int(minute.attrs.get('invalid_timestamp_rows_excluded',0)))
        write(manifest_path, manifest)
        if n % 16 == 0 or n == len(jobs):
            print(f'Fresh validation collection {n}/{len(jobs)}',flush=True)
    manifest['completed_at_utc'] = datetime.now(timezone.utc).isoformat(); manifest['status'] = 'complete'; write(manifest_path,manifest)
    verify_seal(out); old_freezes()


def evaluate(out):
    verify_seal(out)
    if (out / 'summary.json').exists(): raise FileExistsError('Preserve completed evaluation; audit rather than rescore')
    manifest = read(out / 'download_manifest.json'); assert manifest['status'] == 'complete'
    plan = read(out / 'plan.json'); jobs = list(daily_requests(plan,plan['development_start_kst'],plan['development_end_kst'],window_minutes=plan['window_minutes']))
    assert len(manifest['records']) == len(jobs)
    frames = []
    for identifier,r in manifest['records'].items():
        p = out / 'observations' / (identifier + '.parquet'); assert sha(p) == r['sha256']; frames.append(pd.read_parquet(p))
    observed = pd.concat(frames,ignore_index=True); assert not observed.duplicated(['station','time']).any()
    prediction = pd.read_parquet(out / 'predictions.parquet')
    evaluation = prediction.merge(observed[['station','time','ice','state_raw','road_temp','lat','lon','elevation_m']],on=['station','time'],how='left',validate='one_to_one',indicator=True)
    assert len(evaluation) == len(prediction)
    evaluation.to_parquet(out / 'evaluation.parquet',index=False,compression='zstd')
    metrics={}; station_rows=[]; days=[]; events=[]
    for policy in plan['frozen_policies']:
        result,station,day,event = diagnostic_report(evaluation,evaluation[policy]); metrics[policy]=result
        for value,store in [(station,station_rows),(day,days),(event,events)]: value['policy']=policy;store.append(value)
    temperature={policy:temperature_report(evaluation,evaluation[policy]) for policy in plan['temperature_comparison']}
    pd.concat(station_rows).to_csv(out / 'station_metrics.csv',index=False);pd.concat(days).to_csv(out / 'daily_metrics.csv',index=False);pd.concat(events).to_csv(out / 'event_metrics.csv',index=False)
    coverage=[]; catalog=pd.read_csv(out / 'points.csv',dtype={'station':str}).set_index('station')
    for station,part in evaluation.groupby('station'):
        d=(part.lat-catalog.loc[station,'lat']).abs();e=(part.lon-catalog.loc[station,'lon']).abs()
        coverage.append(dict(station=station,group=part.group.iloc[0],planned_rows=len(part),received_rows=int(part._merge.eq('both').sum()),
                             valid_state_rows=int(part.ice.notna().sum()),ice_rows=int(part.ice.eq(1).sum()),
                             valid_temperature_rows=int((part.road_temp.notna() & part.weather_hgb23.notna()).sum()),
                             max_lat_difference=float(d.max()) if d.notna().any() else None,max_lon_difference=float(e.max()) if e.notna().any() else None,
                             response_elevations_m=sorted(part.elevation_m.dropna().unique().tolist())))
    write(out / 'coverage.json',coverage)
    b=metrics['original_ice'];c=metrics['thermal_moisture']
    write(out / 'summary.json',dict(status='one_time_fresh_station_evaluation_complete',evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
                                   metrics=metrics,temperature=temperature,planned_rows=len(prediction),received_rows=len(observed),
                                   joint_fp_fn_improvement=c['fp']<b['fp'] and c['fn']<b['fn'],
                                   evaluation_sha256=sha(out / 'evaluation.parquet'),protected_or_opened_future_labels_used=False,
                                   source_scope='New-station spatial test, same first winter; not official or future-winter validation.',retuning_permitted=False))
    old_freezes();print(json.dumps(read(out / 'summary.json'),ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=['prepare','collect','evaluate']);parser.add_argument('--output',type=Path,default=DEFAULT_OUT);parser.add_argument('--credentials-file',type=Path)
    args=parser.parse_args();out=args.output.resolve()
    if not out.is_relative_to(PRIVATE.resolve()): parser.error('Private local output required')
    if args.phase=='prepare': prepare(out)
    elif args.phase=='collect': collect(out,args.credentials_file)
    else: evaluate(out)


if __name__=='__main__':main()
