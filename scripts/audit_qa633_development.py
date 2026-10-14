"""독립 NumPy 혼동행렬·직접 날짜/지점 평균으로 Q&A633 재집계를 검산한다."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import read, write, preservation
from scripts.audit_temperature_blind_validation import compare

OUT = ROOT / 'outputs/private/qa633_development_20261013_v1'


def reference(frame, name, pop, minimum):
    y, p = frame.ice.to_numpy(float), frame[name].to_numpy(float); valid = np.isfinite(y)
    station_id = frame.station.map({s: i for i, s in enumerate(pop)}).to_numpy(int)
    day_id = (frame.time.dt.normalize()-pd.Timestamp('2024-11-01')).dt.days.to_numpy(int)
    ids = station_id*120+day_id; length = len(pop)*120
    assert np.isin(y[valid], [0, 1]).all() and np.isin(p, [0, 1]).all() and ((day_id >= 0) & (day_id < 120)).all()
    n = np.bincount(ids[valid], minlength=length)
    counts = {key: np.bincount(ids[valid & (y == a) & (p == b)], minlength=length) for key, a, b in [('tp', 1, 1), ('fp', 0, 1), ('fn', 1, 0), ('tn', 0, 0)]}
    tp, fp, fn = (counts[k] for k in ['tp', 'fp', 'fn'])
    actual, predicted, active = tp+fn, tp+fp, tp+fp+fn; accepted = n >= minimum
    values = {}
    for metric, numerator, denom in [('precision', tp, predicted), ('recall', tp, actual), ('f1', 2*tp, 2*tp+fp+fn)]:
        result = np.full(length, np.nan); use = accepted & (denom > 0)
        result[use] = numerator[use]/denom[use]; values[metric] = result
    row_records = []
    for i, station in enumerate(pop):
        ids_s = np.arange(i*120, (i+1)*120); covered = accepted[ids_s]
        record = dict(station=station, planned_days=120, coverage_days=int(covered.sum()),
            active_days=int((covered & (active[ids_s] > 0)).sum()), both_zero_days=int((covered & (active[ids_s] == 0)).sum()),
            miss_only_days=int((covered & (actual[ids_s] > 0) & (predicted[ids_s] == 0)).sum()),
            false_alarm_only_days=int((covered & (actual[ids_s] == 0) & (predicted[ids_s] > 0)).sum()),
            excluded_ice_days=int((~covered & (actual[ids_s] > 0)).sum()))
        for metric, v in values.items():
            usable = v[ids_s][np.isfinite(v[ids_s])]
            record[metric+'_days'] = len(usable); record[metric] = float(sum(usable)/len(usable)) if len(usable) else None
        row_records.append(record)
    summary = dict(population_stations=len(pop), planned_days=length, coverage_days=int(accepted.sum()),
        active_days=int((accepted & (active > 0)).sum()), both_zero_days=int((accepted & (active == 0)).sum()),
        miss_only_days=int((accepted & (actual > 0) & (predicted == 0)).sum()),
        false_alarm_only_days=int((accepted & (actual == 0) & (predicted > 0)).sum()), excluded_ice_days=int((~accepted & (actual > 0)).sum()),
        confirmed_missed_day_policy=True, minimum_coverage_officially_confirmed=False,
        false_alarm_only_recall_explicitly_answered=False, official_competition_score=False)
    for metric in values:
        v = [r[metric] for r in row_records if r[metric] is not None]
        summary[metric+'_days'] = int(np.isfinite(values[metric]).sum()); summary[metric+'_stations'] = len(v)
        summary[metric+'_available_station_mean'] = float(sum(v)/len(v)) if v else None
        summary[metric+'_all_population_station_mean'] = float(sum(v)/len(v)) if len(v) == len(pop) else None
    daily = pd.DataFrame({'station': np.repeat(pop, 120), 'date_kst': np.tile(pd.date_range('2024-11-01', periods=120, freq='D'), len(pop)),
        'valid_slots': n, **counts, 'actual_ice_slots': actual, 'predicted_ice_slots': predicted, 'metric_active_slots': active,
        'coverage_accepted': accepted, 'expected_slots': 144, 'both_zero': active == 0,
        'miss_only': (actual > 0) & (predicted == 0), 'false_alarm_only': (actual == 0) & (predicted > 0), **values})
    for metric, value in values.items(): daily['included_'+metric] = np.isfinite(value)
    return summary, pd.DataFrame(row_records), daily


def main():
    target = OUT / 'independent_verification.json'
    if target.exists(): raise FileExistsError('Preserve completed policy audit')
    s = read(OUT / 'summary.json'); signatures = read(OUT / 'input_signatures.json')
    for rel, digest in signatures.items(): assert sha(ROOT / rel) == digest, rel
    for rel, digest in s['files'].items(): assert sha(OUT / rel) == digest, rel
    frame = pd.read_parquet(OUT / 'fixed_predictions.parquet'); records = read(OUT / 'source_records.json'); checked = 0
    assert set(frame.station) == set(s['population']) and len(frame) == s['rows'] == 155257 and frame.ice.notna().sum() == 155118
    assert frame.time.ge('2024-11-01').all() and frame.time.lt('2025-03-01').all() and not frame.duplicated(['station', 'time']).any()
    for name, record in records.items():
        f = pd.read_parquet(ROOT / record['source'], columns=['station', 'time', 'ice', record['column']]).sort_values(['station', 'time']).reset_index(drop=True)
        pd.testing.assert_frame_equal(f[['station', 'time', 'ice']], frame[['station', 'time', 'ice']])
        np.testing.assert_array_equal(f[record['column']], frame[name]); checked += len(frame)
    saved_days = pd.read_csv(OUT / 'research_daily_metrics.csv', dtype={'station': str}, parse_dates=['date_kst'])
    saved_stations = pd.read_csv(OUT / 'research_station_metrics.csv', dtype={'station': str}); comparisons = []
    for name in s['methods']:
        for minimum in [144, 130, 72, 1]:
            expected, stations, days = reference(frame, name, s['population'], minimum)
            compare(expected, s['reports'][name][str(minimum)])
            ds = saved_days.loc[saved_days.method.eq(name) & saved_days.minimum_valid_slots.eq(minimum)].reset_index(drop=True)
            st = saved_stations.loc[saved_stations.method.eq(name) & saved_stations.minimum_valid_slots.eq(minimum)].reset_index(drop=True)
            pd.testing.assert_frame_equal(ds[days.columns], days, check_exact=False, atol=1e-12, rtol=0)
            pd.testing.assert_frame_equal(st[stations.columns], stations, check_exact=False, atol=1e-12, rtol=0)
            if minimum == 144:
                wrong = days.loc[days.coverage_accepted & days.actual_ice_slots.gt(0) & days.predicted_ice_slots.gt(0)].groupby('station').f1.mean()
                comparisons.append(dict(method=name, correct_f1=expected['f1_available_station_mean'], wrong_joint_defined_f1=float(wrong.mean()) if len(wrong) else None,
                    wrongly_excluded_missed_days=expected['miss_only_days'], wrongly_excluded_false_alarm_days=expected['false_alarm_only_days'],
                    precision_days=expected['precision_days'], recall_days=expected['recall_days'], f1_days=expected['f1_days']))
    pd.testing.assert_frame_equal(pd.read_csv(OUT / 'wrong_intersection_comparison.csv'), pd.DataFrame(comparisons), check_exact=False, atol=1e-12, rtol=0)
    freezes = preservation()
    result = dict(status='independent_qa633_metrics_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
        summary_sha256=sha(OUT / 'summary.json'), audit_source_sha256=sha(Path(__file__)), fixed_prediction_values_verified=checked,
        daily_rows_verified=len(saved_days), station_rows_verified=len(saved_stations), method_coverage_reports_verified=84,
        previous_metrics_unchanged=True, new_model_fits=0, changed_thresholds=0, assessment_outcomes_used=False,
        old_frozen_files=freezes[0], reserved_frozen_files=freezes[1])
    write(target, result); print(result)


if __name__ == '__main__': main()
