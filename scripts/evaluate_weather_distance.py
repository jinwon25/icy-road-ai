"""거리 두 변수만 제거해 동일 입력·그룹·학습 조건에서 중첩 공간 비교한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.evidence_review import review_domain
from src.temperature_transfer import WEATHER_FEATURES, regression_report, select_temperature
from src.weather_distance_ablation import CANDIDATE, DISTANCE_FREE_FEATURES, REMOVED_FEATURES, training_values, predict
from src.thermal_ice import fixed_thermal_rule, diagnostic_report
from scripts.fresh_station_validation import old_freezes, verify_seal

PRIVATE = ROOT / 'outputs/private'
PREVIOUS = PRIVATE / 'temperature_loss_20261010_v1'
BASELINE = PRIVATE / 'weather_fallback_20261009_v1'
CONFIG = ROOT / 'config/weather_distance_experiment.json'
DEFAULT = PRIVATE / 'weather_distance_20261010_v1'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, data):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')


def preservation():
    result = old_freezes()
    verify_seal(PRIVATE / 'temperature_blind_20261010_v1')
    verify_seal(PRIVATE / 'fresh_station_validation_20261009_v2')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT)
    out = parser.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to(PRIVATE.resolve()):
        raise ValueError('New private experiment directory required')
    config = read(CONFIG)
    if config['candidate'] != CANDIDATE or config['removed_features'] != list(REMOVED_FEATURES):
        raise ValueError('Fixed ablation contract differs')
    freezes = preservation()
    source_summary = read(PREVIOUS / 'summary.json')
    if read(PREVIOUS / 'independent_verification.json')['status'] != 'independent_temperature_audit_passed':
        raise ValueError('Audited source experiment required')
    for rel in ['development_inputs.parquet', 'groups.json', 'outer_predictions.parquet']:
        if sha(PREVIOUS / rel) != source_summary['files'][rel]:
            raise ValueError('Development evidence changed')
    data = review_domain(pd.read_parquet(PREVIOUS / 'development_inputs.parquet'))
    groups = {g: set(v) for g, v in read(PREVIOUS / 'groups.json').items()}
    external = set().union(*groups.values())
    if len(external) != 9 or len(set(data.station) - external) != 14 or len(groups) != 4:
        raise ValueError('Only existing 23 development stations required')
    excluded = {'12410', '33411', '23402', '12104', '12206', '12212', '12407', '23206', '23406', '33209', '33415',
                '12406', '23405', '33407', '33416'}
    if set(data.station) & excluded:
        raise ValueError('Already opened assessment station in development')
    old_fits = [r for r in read(BASELINE / 'fit_receipts.json') if r['candidate'] == 'augmented_hgb']
    baselines = {}
    sources = [CONFIG, Path(__file__), ROOT / 'src/weather_distance_ablation.py', ROOT / 'src/evidence_review.py',
               ROOT / 'src/temperature_transfer.py', ROOT / 'src/thermal_ice.py', BASELINE / 'fit_receipts.json',
               *(PREVIOUS / r for r in ['summary.json', 'independent_verification.json', 'development_inputs.parquet',
                                        'groups.json', 'outer_predictions.parquet']),
               PRIVATE / 'daily_primary_transfer_20261009_v1/predictions.parquet']
    for receipt in old_fits:
        key = tuple(receipt['forbidden_stations']); path = BASELINE / receipt['model_path']
        if sha(path) != receipt['model_sha256'] or receipt['features'] != WEATHER_FEATURES:
            raise ValueError('Baseline model signature differs')
        expected = data.loc[np.isfinite(data.road_temp) & np.isfinite(data.asos_air_temp) & ~data.station.isin(key)]
        if len(expected) != receipt['training_rows'] or sorted(expected.station.unique()) != receipt['training_stations']:
            raise ValueError('Baseline training population differs')
        baselines.setdefault(key, (path, receipt)); sources.append(path)
    signatures = {str(p.relative_to(ROOT)): sha(p) for p in set(sources)}
    out.mkdir()
    write(out / 'experiment_plan.json', config | {'started_at_utc': datetime.now(timezone.utc).isoformat(),
                                                'new_independent_assessment': False})
    write(out / 'input_signatures.json', signatures)
    shutil.copy2(__file__, out / 'analysis_source.py')
    shutil.copy2(ROOT / 'src/weather_distance_ablation.py', out / 'ablation_source.py')
    write(out / 'groups.json', {g: sorted(v) for g, v in groups.items()})
    data.to_parquet(out / 'development_inputs.parquet', index=False, compression='zstd')
    cache, receipts, reuse, decisions, parts = {}, [], [], {}, []

    def baseline(forbidden, query):
        key = tuple(sorted(forbidden)); path, receipt = baselines[key]
        model = joblib.load(path)
        if any(model.get_params().get(k) != v for k, v in config['hgb_parameters'].items()):
            raise ValueError('Baseline and candidate hyperparameters differ')
        pred = np.where(query.asos_air_temp.notna(), model.predict(query[WEATHER_FEATURES]), np.nan)
        reuse.append(dict(path=str(path), sha256=sha(path), forbidden_stations=list(key)))
        return pred

    def fit(forbidden):
        key = tuple(sorted(forbidden))
        if key in cache:
            return cache[key]
        train = data.loc[np.isfinite(data.road_temp) & np.isfinite(data.asos_air_temp) & ~data.station.isin(key)].copy()
        x, y = training_values(train, key)
        folder = out / 'models' / ('excluded_' + '_'.join(key)); folder.mkdir(parents=True)
        started = time.monotonic()
        model = HistGradientBoostingRegressor(**config['hgb_parameters']); model.fit(x, y)
        joblib.dump(model, folder / 'model.joblib', compress=3)
        record = dict(candidate=CANDIDATE, forbidden_stations=list(key), features=list(DISTANCE_FREE_FEATURES),
                      training_rows=len(train), training_stations=sorted(train.station.unique()),
                      training_values_sha256=hashlib.sha256(pd.util.hash_pandas_object(train, index=True).to_numpy().tobytes()).hexdigest(),
                      parameters=config['hgb_parameters'], model_path=(folder / 'model.joblib').relative_to(out).as_posix(),
                      model_sha256=sha(folder / 'model.joblib'), fit_seconds=time.monotonic() - started)
        receipts.append(record); write(folder / 'fit_manifest.json', record); cache[key] = model
        print('거리 제거 학습 완료:', ','.join(key), round(record['fit_seconds'], 2), flush=True)
        return model

    with threadpool_limits(limits=config['max_compute_threads']):
        for outer, held in groups.items():
            query = data.loc[data.station.isin(external - held)]
            inner = query[['station', 'time', 'road_temp']].copy()
            inner['direct_weather14'] = np.nan; inner[CANDIDATE] = np.nan
            for group, checked in groups.items():
                if group == outer:
                    continue
                target = query.loc[query.station.isin(checked)]
                inner.loc[target.index, 'direct_weather14'] = baseline(held | checked, target)
                inner.loc[target.index, CANDIDATE] = predict(fit(held | checked), target)
            expected = np.isfinite(query.asos_air_temp)
            if any(not np.array_equal(np.isfinite(inner[name]), expected) for name in ['direct_weather14', CANDIDATE]):
                raise ValueError('Inner finite prediction denominator differs')
            reports = {name: regression_report(query, inner[name].to_numpy()) for name in ['direct_weather14', CANDIDATE]}
            chosen = select_temperature(reports, candidate_names=[CANDIDATE], maximum_station_harm=config['maximum_station_harm'])
            decision = dict(outer_group=outer, excluded_stations=sorted(held), selection_groups=sorted(set(groups) - {outer}),
                            selected_candidate=chosen, inner_reports=reports, outer_labels_used_for_selection=False)
            folder = out / outer; folder.mkdir()
            write(folder / 'decision.json', decision); decisions[outer] = decision
            inner.to_parquet(folder / 'inner_oof.parquet', index=False, compression='zstd')
            target = data.loc[data.station.isin(held)]
            result = target[['station', 'time', 'group', 'road_temp']].copy()
            result['direct_weather14'] = baseline(held, target)
            result[CANDIDATE] = predict(fit(held), target)
            result['selected_temperature'] = result[chosen]; result['selected_candidate'] = chosen
            result.to_parquet(folder / 'outer_predictions.parquet', index=False, compression='zstd'); parts.append(result)
            print(outer, '선택:', chosen, flush=True)
    combined = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    reference = pd.read_parquet(PREVIOUS / 'outer_predictions.parquet').set_index(['station', 'time'])
    paired = reference.loc[pd.MultiIndex.from_frame(combined[['station', 'time']])]
    np.testing.assert_allclose(combined.direct_weather14, paired.direct_weather14, rtol=0, atol=1e-12, equal_nan=True)
    domain = np.isfinite(combined.direct_weather14)
    for name in [CANDIDATE, 'selected_temperature']:
        if not np.array_equal(domain, np.isfinite(combined[name])):
            raise ValueError('Outer finite prediction denominator differs')
    metrics = {name: regression_report(combined, combined[name].to_numpy()) for name in
               ['direct_weather14', CANDIDATE, 'selected_temperature']}
    pd.DataFrame([dict(variant=name, station=s, **m) for name, report in metrics.items()
                  for s, m in report['stations'].items()]).to_csv(out / 'station_metrics.csv', index=False, encoding='utf-8-sig')
    combined.to_parquet(out / 'outer_predictions.parquet', index=False, compression='zstd')
    # 온도 결과에 관계없이 사전 등록한 고정 수분 규칙을 같은 전체 행에서 보고한다.
    labels = review_domain(pd.read_parquet(PRIVATE / 'daily_primary_transfer_20261009_v1/predictions.parquet'))
    paired_inputs = combined[['station', 'time']].merge(data[['station', 'time', 'aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']],
                                                       on=['station', 'time'], validate='one_to_one')
    classified = combined.merge(labels[['station', 'time', 'ice', 'baseline_prediction']], on=['station', 'time'], validate='one_to_one')
    if len(classified) != len(combined) or not combined[['station', 'time']].equals(classified[['station', 'time']]):
        raise ValueError('Diagnostic population differs')
    if not classified[['station', 'time']].equals(paired_inputs[['station', 'time']]):
        raise ValueError('Moisture input alignment differs')
    ice_metrics = {}
    for name in ['direct_weather14', CANDIDATE, 'selected_temperature']:
        p, fallback, _ = fixed_thermal_rule(classified[name].to_numpy(), paired_inputs, classified.baseline_prediction.to_numpy(), True)
        classified['ice_' + name] = p
        report, stations, days, events = diagnostic_report(classified, p)
        ice_metrics[name] = report | {'fallback_rows': int(fallback.sum())}
        stations.to_csv(out / f'ice_stations_{name}.csv', index=False, encoding='utf-8-sig')
        days.to_csv(out / f'ice_days_{name}.csv', index=False, encoding='utf-8-sig')
        events.to_csv(out / f'ice_events_{name}.csv', index=False, encoding='utf-8-sig')
    classified.to_parquet(out / 'ice_diagnostic_predictions.parquet', index=False, compression='zstd')
    write(out / 'decisions.json', decisions); write(out / 'fit_receipts.json', receipts); write(out / 'baseline_reuse.json', reuse)
    if len(receipts) != 10 or preservation() != freezes:
        raise ValueError('Fit population or existing seals differ')
    for rel, digest in signatures.items():
        if sha(ROOT / rel) != digest:
            raise ValueError('Original source changed')
    summary = dict(status='distance_ablation_nested_development_complete', completed_at_utc=datetime.now(timezone.utc).isoformat(),
                   input_rows=len(data), outer_rows=len(combined), metrics=metrics, ice_diagnostic=ice_metrics,
                   choices={g: d['selected_candidate'] for g, d in decisions.items()}, unique_new_fits=len(receipts),
                   old_frozen_files=freezes[0], reserved_frozen_files=freezes[1], protected_or_assessment_outcomes_used=False,
                   final_model_promoted=False, files={p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    write(out / 'summary.json', summary)
    print('개발 거리 제거 비교 완료:', len(combined), '행, 학습', len(receipts), '건', flush=True)


if __name__ == '__main__':
    main()
