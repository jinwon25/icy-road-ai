"""누적합 시간탐색·저장모델 재예측·별도 집계로 기상 이력 연구를 검산한다."""
from datetime import datetime, timezone
import hashlib
from itertools import combinations
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import read, write, preservation
from scripts.audit_method_blending import report, gate
from scripts.audit_temperature_blind_validation import compare, reference_ice
from scripts.audit_temperature_uncertainty import radius, report as range_report

PRIVATE = ROOT / 'outputs/private'
OUT = PRIVATE / 'weather_memory_temperature_20261013_v1'
BASE = PRIVATE / 'temperature_pair_blending_20261010_v1'
BASELINE = 'equal_distance_mse_mae300'
MODELS = ['memory12_mse300', 'memory12_mae300']
CANDIDATES = MODELS+['equal_memory_pair', 'equal_trio_memory']
CURRENT = ['asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_wind_speed', 'aws_rain_15m', 'aws_dewpoint', 'aws_age_minutes', 'asos_age_minutes', 'hour_sin', 'hour_cos', 'season_sin', 'season_cos']
HISTORY = ['asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_dewpoint', 'aws_rain_15m', 'aws_wind_speed']
NAMES = [f'{c}_past_mean_{m}m' for c in HISTORY for m in [60, 180, 720]]+[f'{c}_change_{m}m' for c in HISTORY for m in [60, 180]]
FEATURES = CURRENT+NAMES


def reference_history(data):
    result = pd.DataFrame(np.nan, index=data.index, columns=NAMES)
    for _, f in data.groupby('station', sort=False):
        f = f.sort_values('time'); t = f.time.to_numpy(dtype='datetime64[ns]')
        positions = np.arange(len(t))
        for c in HISTORY:
            v = f[c].to_numpy(float); valid = np.isfinite(v)
            total = np.r_[0., np.cumsum(np.where(valid, v, 0.))]
            counts = np.r_[0, np.cumsum(valid)]
            for minutes in [60, 180, 720]:
                left = np.searchsorted(t, t-np.timedelta64(minutes, 'm'), side='left')
                n = counts[positions]-counts[left]
                sums = total[positions]-total[left]
                means = np.divide(sums, n, out=np.full(len(v), np.nan), where=n >= np.ceil(.8*minutes/10))
                result.loc[f.index, f'{c}_past_mean_{minutes}m'] = means
            for minutes in [60, 180]:
                wanted = t-np.timedelta64(minutes, 'm'); ids = np.searchsorted(t, wanted)
                exact = (ids < len(t)) & (t[np.minimum(ids, len(t)-1)] == wanted)
                previous = np.full(len(v), np.nan); previous[exact] = v[ids[exact]]
                result.loc[f.index, f'{c}_change_{minutes}m'] = v-previous
    return result


def bins(f, name):
    p = f[name].to_numpy(float); result = np.full(len(f), None, dtype=object)
    hours = f.time.dt.hour.to_numpy()
    for category, temperature in [('cold', p < -2), ('transition', (p >= -2) & (p <= 2)), ('warm', p > 2)]:
        for light, clock in [('day', (hours >= 6) & (hours < 18)), ('night', (hours < 6) | (hours >= 18))]:
            result[temperature & clock & np.isfinite(p)] = category+'_'+light
    return pd.Series(result, index=f.index)


def interval_metrics(f, name, key):
    q = f[['station', 'time', 'road_temp', name, key+'_lower', key+'_upper']].rename(columns={key+'_lower': name+'_lower', key+'_upper': name+'_upper'})
    return range_report(q, name)


def ice_checks(c, b, cs, bs):
    cs, bs = cs.set_index('station'), bs.set_index('station')
    for k in ['n', 'complete_days', 'fixed_ice_days', 'fixed_ice_day_stations', 'events', 'single_slot_events']: assert c[k] == b[k]
    assert set(cs.index) == set(bs.index) and cs.n.eq(bs.n).all() and (cs.tp+cs.fn).eq(bs.tp+bs.fn).all()
    metrics = ['f1', 'fixed_station_f1_zero_undefined', 'fixed_ice_day_f1', 'provisional_daily_station_f1']
    supported = all(c[k] is not None and b[k] is not None for k in metrics)
    checks = dict(supported_metrics=supported, fp_nonincrease=c['fp'] <= b['fp'], fn_nonincrease=c['fn'] <= b['fn'],
                  every_positive_station_tp=bool(cs.loc[(bs.tp+bs.fn) > 0, 'tp'].ge(bs.loc[(bs.tp+bs.fn) > 0, 'tp']).all()),
                  events_nonincrease_misses=c['detected_events'] >= b['detected_events'],
                  singles_nonincrease_misses=c['detected_single_slot_events'] >= b['detected_single_slot_events'],
                  f1_nonworse=supported and all(c[k]+1e-12 >= b[k] for k in metrics),
                  strict_improvement=supported and (c['fp'] < b['fp'] or c['fn'] < b['fn'] or any(c[k] > b[k]+1e-12 for k in metrics)))
    return dict(eligible=all(checks.values()), checks=checks)


def main():
    target = OUT / 'independent_verification.json'
    if target.exists(): raise FileExistsError('Preserve completed audit')
    summary = read(OUT / 'summary.json'); groups = read(OUT / 'groups.json'); plan = read(OUT / 'experiment_plan.json')
    for rel, digest in read(OUT / 'input_signatures.json').items(): assert sha(ROOT / rel) == digest, rel
    for rel, digest in summary['files'].items(): assert sha(OUT / rel) == digest, rel
    data = pd.read_parquet(PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet')
    assert set(data.station) == set(plan['allowed_stations']) and data.time.ge('2024-11-01').all() and data.time.lt('2025-03-01').all()
    expected = reference_history(data); saved = pd.read_parquet(OUT / 'history_inputs.parquet')
    pd.testing.assert_index_equal(expected.index, saved.index)
    assert list(saved) == NAMES
    np.testing.assert_allclose(saved, expected, atol=2e-9, rtol=0, equal_nan=True)
    d = pd.concat([data, expected], axis=1); pred_values = 0; refits = 0
    original_features = pd.concat([data, saved], axis=1)
    receipts = read(OUT / 'fit_receipts.json')
    contexts = {(g,) for g in groups} | set(combinations(sorted(groups), 2))
    assert len(receipts) == 20 and {(tuple(r['excluded_groups']), r['candidate']) for r in receipts} == {(c, m) for c in contexts for m in MODELS}
    with threadpool_limits(limits=2):
        for r in receipts:
            excluded = tuple(r['excluded_groups']); forbidden = set().union(*(set(groups[g]) for g in excluded))
            fit = d.loc[np.isfinite(d.road_temp) & np.isfinite(d.asos_air_temp) & ~d.station.isin(forbidden)]
            query = d.loc[d.station.isin(forbidden)]
            assert len(fit) == r['training_rows'] and sorted(fit.station.unique()) == r['training_stations'] and sorted(forbidden) == r['forbidden_stations']
            assert r['features'] == FEATURES and not set(fit.station) & forbidden
            digest = hashlib.sha256(pd.util.hash_pandas_object(original_features.loc[fit.index, ['station', 'time', 'road_temp', *FEATURES]], index=True).to_numpy().tobytes()).hexdigest()
            assert digest == r['training_values_sha256']
            path = OUT / r['model_path']; assert sha(path) == r['model_sha256']
            model = joblib.load(path)
            params = plan['hgb_parameters'] | {'loss': 'squared_error' if r['candidate'] == MODELS[0] else 'absolute_error'}
            assert r['parameters'] == params and all(model.get_params()[k] == v for k, v in params.items())
            stored = pd.read_parquet(path.parent / 'predictions.parquet')
            pd.testing.assert_frame_equal(stored[['station', 'time']], query[['station', 'time']].reset_index(drop=True))
            # 별도 누적합의 미세한 반올림으로 트리 경계가 바뀌지 않도록, 재예측은 검산한 저장 입력을 쓴다.
            replay = np.where(np.isfinite(query.asos_air_temp), model.predict(original_features.loc[query.index, FEATURES]), np.nan)
            np.testing.assert_allclose(stored[r['candidate']], replay, atol=1e-10, rtol=0, equal_nan=True); pred_values += len(query)
            if len(excluded) == 2 and excluded == tuple(sorted(groups)[:2]):
                refit = HistGradientBoostingRegressor(**params).fit(original_features.loc[fit.index, FEATURES], fit.road_temp)
                np.testing.assert_allclose(refit.predict(original_features.loc[query.index, FEATURES]), model.predict(original_features.loc[query.index, FEATURES]), atol=1e-10, rtol=0); refits += 1
            print('모델 검산:', '__'.join(excluded), r['candidate'], flush=True)
    combined = pd.read_parquet(OUT / 'outer_predictions.parquet'); decisions = read(OUT / 'decisions.json'); cals = read(OUT / 'calibrations.json')
    quantiles = 0; bounds = 0; blend_values = 0; parts = []
    for g in groups:
        inner = pd.read_parquet(OUT / g / 'inner_oof.parquet'); outer = pd.read_parquet(OUT / g / 'outer_predictions.parquet')
        assert set(inner.station) == set().union(*(set(groups[h]) for h in groups if h != g)) and set(outer.station) == set(groups[g])
        for kind, f in [('inner_oof', inner), ('outer_predictions', outer)]:
            baseline = pd.read_parquet(BASE / g / (kind+'.parquet'), columns=['station', 'time', 'group', 'road_temp', 'weather_mse300', BASELINE])
            pd.testing.assert_frame_equal(f[baseline.columns], baseline)
            for h in sorted(set(groups)-{g}) if kind == 'inner_oof' else [g]:
                context = '__'.join(sorted([g, h])) if kind == 'inner_oof' else g
                q = pd.read_parquet(OUT / 'contexts' / context / 'predictions.parquet').set_index(['station', 'time'])
                subset = f.loc[f.station.isin(groups[h])]
                expected = q.loc[pd.MultiIndex.from_frame(subset[['station', 'time']]), MODELS]
                np.testing.assert_allclose(subset[MODELS], expected, atol=0, rtol=0, equal_nan=True)
            np.testing.assert_allclose(f.equal_memory_pair, (f[MODELS[0]]+f[MODELS[1]])/2, atol=0, rtol=0, equal_nan=True)
            np.testing.assert_allclose(f.equal_trio_memory, (f[BASELINE]+f.equal_memory_pair)/2, atol=0, rtol=0, equal_nan=True); blend_values += len(f)*2
        reports = {c: report(inner, c) for c in [BASELINE, *CANDIDATES]}; compare(reports, decisions[g]['inner_reports'])
        eligible = [c for c in CANDIDATES if gate(reports[c], reports[BASELINE])]
        chosen = min(eligible, key=lambda c: (reports[c]['station_macro']['mae'], reports[c]['station_macro']['rmse'], c)) if eligible else BASELINE
        assert chosen == decisions[g]['selected_candidate'] and not decisions[g]['outer_labels_used']
        np.testing.assert_allclose(outer.selected_temperature, outer[chosen], rtol=0, atol=0, equal_nan=True)
        for name in [BASELINE, *CANDIDATES]:
            global_r = radius(inner, name)
            for conditional in (False, True):
                key = name+('_conditional' if conditional else '_global'); cal = cals[g][key]
                compare(global_r, cal['global']['radius']); quantiles += 1
                assert cal['calibration_groups'] == sorted(set(groups)-{g}) and not cal['outer_labels_used'] and not cal['guaranteed_coverage']
                widths = np.full(len(outer), global_r)
                if conditional:
                    ib, ob = bins(inner, name), bins(outer, name)
                    for cell, value in cal['conditions'].items():
                        mask = ib.eq(cell) & np.isfinite(inner.road_temp)
                        sub = inner.loc[mask]; eligible = len(sub) >= 500 and sub.station.nunique() >= 2
                        r = radius(sub, name) if eligible else global_r
                        compare(r, value['radius']); quantiles += 1
                        assert value['fallback_to_global'] == (not eligible) and value['calibration_n'] == len(sub) and value['calibration_stations'] == sorted(sub.station.unique())
                        widths[ob.eq(cell)] = r
                np.testing.assert_allclose(outer[key+'_lower'], outer[name]-widths, atol=1e-12, rtol=0, equal_nan=True)
                np.testing.assert_allclose(outer[key+'_upper'], outer[name]+widths, atol=1e-12, rtol=0, equal_nan=True); bounds += len(outer)*2
        parts.append(outer)
    pd.testing.assert_frame_equal(combined, pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True))
    compare({c: report(combined, c) for c in summary['metrics']}, summary['metrics'])
    assert summary['temperature_gate_vs_trio'] == {c: gate(summary['metrics'][c], summary['metrics'][BASELINE]) for c in [*CANDIDATES, 'selected_temperature']}
    conditions = []
    for name in [BASELINE, *CANDIDATES]:
        for conditional in (False, True):
            key = name+('_conditional' if conditional else '_global'); r = interval_metrics(combined, name, key); compare(r, summary['ranges'][key])
            b = bins(combined, name); valid = np.isfinite(combined.road_temp) & np.isfinite(combined[name])
            for cell in sorted(b[valid].unique()):
                mask = valid & b.eq(cell); y, lo, hi = (combined.loc[mask, c].to_numpy() for c in ['road_temp', key+'_lower', key+'_upper'])
                conditions.append(dict(method=key, condition=cell, n=int(mask.sum()), coverage=float(np.mean((lo <= y) & (y <= hi))), width=float(np.mean(hi-lo))))
        c, b = summary['ranges'][name+'_conditional'], summary['ranges'][name+'_global']
        eligible = c['station_macro_coverage'] >= .89 and min(s['coverage'] for s in c['stations'].values()) >= .80 and c['near_freezing']['coverage'] >= .90 and c['mean_interval_score'] < b['mean_interval_score']-1e-12 and c['mean_width'] <= b['mean_width']*1.10+1e-12
        assert eligible == summary['conditional_range_gate'][name]
    pd.testing.assert_frame_equal(pd.DataFrame(conditions), pd.read_csv(OUT / 'range_conditions.csv'), check_exact=False, atol=1e-12, rtol=0)
    # 기존 전역 평균 범위의 결과도 그대로 재현한다.
    old_range = read(PRIVATE / 'temperature_uncertainty_20261010_v1/summary.json')
    compare(summary['ranges'][BASELINE+'_global'], old_range['reports'][BASELINE])
    classified = pd.read_parquet(OUT / 'ice_predictions.parquet'); pd.testing.assert_frame_equal(classified[combined.columns], combined)
    old = pd.read_parquet(BASE / 'ice_predictions.parquet', columns=['station', 'time', 'ice', 'baseline_prediction'])
    pd.testing.assert_frame_equal(classified[old.columns], old)
    water = data.set_index(['station', 'time']).loc[pd.MultiIndex.from_frame(classified[['station', 'time']]), ['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
    reports, stations = {}, {}
    for name in [BASELINE, *CANDIDATES, 'selected_temperature']:
        t = classified[name].to_numpy(); fallback = ~np.isfinite(t) | np.isnan(water).all(axis=1)
        p = ((t <= 0) & ((water[:, 0] >= t) | (water[:, 1] > 0) | (water[:, 2] > 0))).astype(int)
        p[fallback] = classified.baseline_prediction.to_numpy()[fallback]
        np.testing.assert_array_equal(p, classified['ice_'+name])
        reports[name] = reference_ice(classified, 'ice_'+name) | {'fallback_rows': int(fallback.sum())}
        stations[name] = pd.read_csv(OUT / f'ice_stations_{name}.csv', dtype={'station': str})
        for s, part in classified.loc[classified.ice.notna()].groupby('station'):
            expected = dict(n=len(part), tp=int(((part.ice == 1) & (part['ice_'+name] == 1)).sum()), fn=int(((part.ice == 1) & (part['ice_'+name] == 0)).sum()), fp=int(((part.ice == 0) & (part['ice_'+name] == 1)).sum()))
            saved = stations[name].set_index('station').loc[s]
            assert all(saved[k] == v for k, v in expected.items())
    compare(reports, summary['ice_diagnostic'])
    compare({c: ice_checks(reports[c], reports[BASELINE], stations[c], stations[BASELINE]) for c in [*CANDIDATES, 'selected_temperature']}, summary['ice_guard_vs_trio'])
    freezes = preservation()
    assert summary['new_model_fits'] == 20 and not summary['assessment_outcomes_used'] and not summary['model_promoted']
    audit = dict(status='independent_weather_memory_temperature_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
                 summary_sha256=sha(OUT / 'summary.json'), audit_source_sha256=sha(Path(__file__)),
                 history_values_verified=len(data)*len(NAMES), model_receipts_verified=len(receipts), model_prediction_values_verified=pred_values,
                 representative_refits=refits, blend_values_verified=blend_values, quantiles_verified=quantiles, interval_bounds_verified=bounds,
                 decisions_verified=4, temperature_reports_verified=7, interval_reports_verified=10, thermal_policies_verified=6,
                 old_frozen_files=freezes[0], reserved_frozen_files=freezes[1], assessment_outcomes_used=False, guaranteed_coverage=False, model_promoted=False)
    write(target, audit); print(audit)


if __name__ == '__main__': main()
