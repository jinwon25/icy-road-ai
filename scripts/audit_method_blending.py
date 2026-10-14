"""저장 모델·세 단계 제외·활성 집합 최적해·개발 지표를 별도로 검산한다."""
import argparse
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.audit_temperature_blind_validation import reference_temperature, reference_ice, compare
from scripts.fresh_station_validation import old_freezes, verify_seal

COMPONENTS = ['direct_weather14', 'weather12_no_distance', 'residual_weather14', 'direct_thermal24', 'residual_thermal24', 'weather_mae100', 'weather_mse300', 'weather_mae300', 'augmented_ridge']
BLENDS = ['equal_nine', 'equal_weather_trio', 'simplex_mse', 'simplex_shrink']
WEATHER = ['asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_wind_speed', 'aws_rain_15m', 'aws_dewpoint', 'aws_age_minutes', 'asos_age_minutes', 'aws_distance_km', 'asos_distance_km', 'hour_sin', 'hour_cos', 'season_sin', 'season_cos']
THERMAL = WEATHER + ['asos_ground_temp', 'asos_cloud_tenths', 'asos_solar_mj_m2', 'asos_rain_mm', 'asos_snow_cm', 'asos_humidity', 'air_min_3h', 'rain15_max_3h', 'air_dewpoint_gap', 'ground_air_gap']
ALLOWED = set('12103 12209 12210 12211 12409 23202 23203 23204 23403 33103 33206 33409 33410 33412 12207 12408 23205 23404 33205 33408 33207 33413 33414'.split())


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def report(frame, column):
    r = reference_temperature(frame, column)
    return {k: r[k] for k in ['pooled', 'stations', 'station_macro']} | {'near_freezing': reference_temperature(frame.loc[frame.road_temp.between(-2, 2)], column)['pooled']}


def gate(c, b):
    assert set(c['stations']) == set(b['stations'])
    assert c['near_freezing']['n'] == b['near_freezing']['n'] > 0
    assert all(c['stations'][s]['n'] == b['stations'][s]['n'] for s in b['stations'])
    return (c['station_macro']['mae'] < b['station_macro']['mae']-1e-12 and c['station_macro']['rmse'] < b['station_macro']['rmse']-1e-12
            and all(c['stations'][s]['mae'] <= b['stations'][s]['mae']*1.05+1e-12 for s in b['stations'])
            and c['near_freezing']['mae'] <= b['near_freezing']['mae']+1e-12)


def reference_qp(frame, penalty):
    p, y = frame[COMPONENTS].to_numpy(), frame.road_temp.to_numpy()
    valid = np.isfinite(p[:, 0]) & np.isfinite(y)
    assert np.all(np.isfinite(p) == np.isfinite(p[:, :1]))
    gram = np.zeros((9, 9)); stations = sorted(frame.loc[valid, 'station'].unique())
    for st in stations:
        mask = valid & frame.station.eq(st).to_numpy(); errors = p[mask]-y[mask, None]
        gram += (errors.T @ errors)/len(errors)/len(stations)
    q = gram + penalty*np.eye(9); b = np.full(9, penalty/9)
    # 모든 비어 있지 않은 활성 집합의 equality 제약 정상점을 열거한다.
    # 9변수의 511경우이므로 SLSQP와 독립적으로 전역 볼록 최적값을 확인할 수 있다.
    best = None
    for size in range(1, 10):
        for support in combinations(range(9), size):
            ids = list(support); system = np.zeros((size+1, size+1))
            system[:size, :size] = q[np.ix_(ids, ids)]; system[:size, -1] = -1
            system[-1, :size] = 1
            solution = np.linalg.lstsq(system, np.r_[b[ids], 1.], rcond=None)[0]
            w = np.zeros(9); w[ids] = solution[:size]
            if w.min() < -1e-8 or abs(w.sum()-1) > 1e-8:
                continue
            value = w @ q @ w - 2*b @ w
            if best is None or value < best:
                best = float(value)
    assert best is not None
    return q, b, best, int(valid.sum())


def names(candidate):
    return [c for c in WEATHER if c not in ['aws_distance_km', 'asos_distance_km']] if candidate == 'weather12_no_distance' else THERMAL if 'thermal24' in candidate else WEATHER


def predict(model, frame, candidate):
    p = model.predict(frame[names(candidate)])
    if candidate.startswith('residual_'):
        p += frame.asos_air_temp.to_numpy()
    return np.where(frame.asos_air_temp.notna(), p, np.nan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, default=ROOT / 'outputs/private/method_blending_20261010_v2')
    out = parser.parse_args().experiment.resolve(); target = out / 'independent_verification.json'
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()) or target.exists():
        raise ValueError('New private audit receipt required')
    summary = read(out / 'summary.json'); plan = read(out / 'experiment_plan.json')
    for rel, digest in read(out / 'input_signatures.json').items():
        assert sha(ROOT / rel) == digest, rel
    for rel, digest in summary['files'].items():
        assert sha(out / rel) == digest, rel
    data = pd.read_parquet(ROOT / 'outputs/private/weather_distance_20261010_v1/development_inputs.parquet')
    assert set(data.station) == ALLOWED and data.time.ge('2024-11-01').all() and data.time.lt('2025-03-01').all()
    groups = {g: set(v) for g, v in read(out / 'groups.json').items()}
    all_external = set().union(*groups.values()); triples, model_predictions = {}, {}
    new_receipts = read(out / 'fit_receipts.json'); reused = read(out / 'reused_model_receipts.json')
    refitted = set(); replayed = 0
    with threadpool_limits(limits=2):
        for r in reused+new_receipts:
            c, forbidden = r['candidate'], set(r['forbidden_stations'])
            train = data.loc[data.road_temp.notna() & data.asos_air_temp.notna() & ~data.station.isin(forbidden)]
            assert len(train) == r['training_rows'] and sorted(train.station.unique()) == r['training_stations']
            assert not set(train.station) & forbidden
            path = out / r['model_path'] if 'excluded_groups' in r else ROOT / r['model_path']
            assert sha(path) == r['model_sha256']
            query = data.loc[data.station.isin(forbidden)]
            model = joblib.load(path); p = predict(model, query, c); replayed += len(p)
            if 'excluded_groups' not in r:
                model_predictions[(c, tuple(sorted(forbidden)))] = pd.Series(p, index=pd.MultiIndex.from_frame(query[['station', 'time']]))
                continue
            excluded = tuple(r['excluded_groups'])
            assert forbidden == set().union(*(groups[g] for g in excluded))
            assert len(excluded) == 3 and r['features'] == names(c)
            assert hashlib.sha256(pd.util.hash_pandas_object(train, index=True).to_numpy().tobytes()).hexdigest() == r['training_values_sha256']
            if excluded not in triples:
                triples[excluded] = pd.read_parquet(out / 'triple_contexts' / '__'.join(excluded) / 'predictions.parquet')
            saved = triples[excluded]
            pd.testing.assert_frame_equal(saved[['station', 'time', 'road_temp']], query[['station', 'time', 'road_temp']].reset_index(drop=True))
            np.testing.assert_allclose(saved[c], p, atol=0, rtol=0, equal_nan=True)
            if c not in refitted:
                if c == 'augmented_ridge':
                    clone = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True), StandardScaler(), Ridge(alpha=100.))
                    clone.fit(train[names(c)], train.road_temp)
                else:
                    clone = HistGradientBoostingRegressor(**r['parameters'])
                    clone.fit(train[names(c)], train.road_temp-(train.asos_air_temp if c.startswith('residual_') else 0))
                np.testing.assert_allclose(predict(clone, query, c), p, atol=1e-10, rtol=0, equal_nan=True); refitted.add(c)
        receipts = read(out / 'meta_fit_receipts.json'); decisions = read(out / 'decisions.json'); parts = []
        meta_checked = 0
        for outer, held in groups.items():
            inner = pd.read_parquet(out / outer / 'inner_oof.parquet'); result = pd.read_parquet(out / outer / 'outer_predictions.parquet')
            assert set(inner.station) == all_external-held and set(result.station) == held
            for frame, stage in [(inner, 'inner'), (result, 'outer')]:
                for check in (set(groups)-{outer} if stage == 'inner' else [outer]):
                    q = frame.loc[frame.group.eq(check)]
                    excluded_stations = held | groups[check] if stage == 'inner' else held
                    keys = pd.MultiIndex.from_frame(q[['station', 'time']])
                    for c in COMPONENTS:
                        # Ridge의 BLAS 행 배치가 다르면 약1e-15 차이가 생길 수 있다.
                        # 온도 단위의 절대1e-10 허용만 적용하며 결측·분모는 동일해야 한다.
                        np.testing.assert_allclose(q[c], model_predictions[(c, tuple(sorted(excluded_stations)))].loc[keys], atol=1e-10, rtol=0, equal_nan=True)
                p = frame[COMPONENTS].to_numpy()
                np.testing.assert_allclose(frame.equal_nine, p.mean(axis=1), atol=1e-12, rtol=0, equal_nan=True)
                np.testing.assert_allclose(frame.equal_weather_trio, frame[['direct_weather14', 'weather12_no_distance', 'weather_mse300']].mean(axis=1, skipna=False), atol=1e-12, rtol=0, equal_nan=True)
            for r in [r for r in receipts if r['outer_group'] == outer]:
                check = r['validation_group']; stage = r['stage']; excluded = {outer} | ({check} if stage == 'inner' else set())
                assert set(r['meta_groups']) == set(groups)-excluded
                if stage == 'inner':
                    fragments = []
                    for k in r['meta_groups']:
                        context = tuple(sorted([outer, check, k]))
                        assert excluded | {k} == set(context)
                        fragments.append(triples[context].loc[triples[context].group.eq(k)])
                    meta = pd.concat(fragments, ignore_index=True); q = inner.loc[inner.group.eq(check)]
                else:
                    meta, q = inner, result
                assert not set(meta.station) & set().union(*(groups[g] for g in excluded))
                assert len(meta) == r['meta_training_rows']
                qmat, b, optimum, count = reference_qp(meta, r['penalty']); w = np.asarray(r['weights'])
                assert w.min() >= 0 and abs(w.sum()-1) <= 1e-10 and count == r['valid_rows']
                np.testing.assert_allclose(w @ qmat @ w-2*b @ w, optimum, atol=1e-7, rtol=0)
                np.testing.assert_allclose(q[r['candidate']], q[COMPONENTS].to_numpy() @ w, atol=1e-12, rtol=0, equal_nan=True)
                meta_checked += 1
            reports = {c: report(inner, c) for c in ['direct_weather14', 'weather_mse300', *BLENDS]}
            compare(reports, decisions[outer]['inner_reports'])
            eligible = [c for c in BLENDS if gate(reports[c], reports['direct_weather14'])]
            selected = min(eligible, key=lambda c: (reports[c]['station_macro']['mae'], reports[c]['station_macro']['rmse'], c)) if eligible else 'direct_weather14'
            assert selected == decisions[outer]['selected_candidate'] and not decisions[outer]['outer_labels_used_for_selection']
            np.testing.assert_allclose(result.selected_temperature, result[selected], atol=0, rtol=0, equal_nan=True); parts.append(result)
            print('검산 완료:', outer, flush=True)
    combined = pd.read_parquet(out / 'outer_predictions.parquet')
    pd.testing.assert_frame_equal(combined, pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True))
    reports = {c: report(combined, c) for c in summary['metrics']}; compare(reports, summary['metrics'])
    for c in summary['development_gate_vs_weather14']:
        assert gate(reports[c], reports['direct_weather14']) == summary['development_gate_vs_weather14'][c]
        assert gate(reports[c], reports['weather_mse300']) == summary['incremental_gate_vs_mse300'][c]
    classified = pd.read_parquet(out / 'ice_predictions.parquet')
    pd.testing.assert_frame_equal(classified[combined.columns], combined)
    water = data.set_index(['station', 'time']).loc[pd.MultiIndex.from_frame(combined[['station', 'time']]), ['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
    for c, r in summary['ice_diagnostic'].items():
        t = classified[c].to_numpy(); fallback = ~np.isfinite(t) | np.isnan(water).all(axis=1)
        p = ((t <= 0) & ((water[:, 0] >= t) | (water[:, 1] > 0) | (water[:, 2] > 0))).astype(int)
        p[fallback] = classified.baseline_prediction.to_numpy()[fallback]
        np.testing.assert_array_equal(p, classified['ice_'+c])
        compare(reference_ice(classified, 'ice_'+c) | {'fallback_rows': int(fallback.sum())}, r)
    correlation = pd.read_csv(out / 'error_correlations.csv', index_col=0)
    valid = combined.road_temp.notna() & combined.direct_weather14.notna()
    errors = combined.loc[valid, COMPONENTS].to_numpy()-combined.loc[valid, 'road_temp'].to_numpy()[:, None]
    np.testing.assert_allclose(correlation, np.corrcoef(errors, rowvar=False), atol=1e-12, rtol=0)
    freezes = old_freezes()
    for name in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1', 'temperature_mean_blind_20261010_v1']:
        verify_seal(ROOT / 'outputs/private' / name)
    assert len(new_receipts) == 36 and len(reused) == 90 and meta_checked == 32 and len(refitted) == 9
    result = dict(status='independent_three_level_blending_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
                  summary_sha256=sha(out / 'summary.json'), audit_source_sha256=sha(Path(__file__)),
                  model_prediction_values_replayed=replayed, new_base_models=36, reused_base_models=90, representative_refits=sorted(refitted),
                  active_set_meta_fits_verified=meta_checked, decisions_verified=4, temperature_variants_verified=len(reports),
                  thermal_policies_verified=len(summary['ice_diagnostic']), old_frozen_files=freezes[0], reserved_frozen_files=freezes[1], model_promoted=False)
    with target.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
