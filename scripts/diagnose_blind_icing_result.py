"""완료된 새 지역 평가의 위치·결측·오경보와 미탐을 설명한다. 모델·주 지표는 바꾸지 않는다."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.blind_icing_validation import DEFAULT, PRIVATE, read, write, verify, now
from scripts.screen_expanded_icing_regions import distances
from src.data_source import sha256_file as sha


def main():
    out = PRIVATE / 'blind_icing_diagnosis_20261025_v1'
    if out.exists():
        raise FileExistsError('Preserve completed diagnosis')
    verify(DEFAULT)
    summary_sha = sha(DEFAULT / 'summary.json')
    audit = read(DEFAULT / 'full_verification.json')
    assert audit['summary_sha256'] == summary_sha
    summary = read(DEFAULT / 'summary.json')
    plan = read(DEFAULT / 'plan.json')
    frame = pd.read_parquet(DEFAULT / 'evaluation.parquet')
    assert sha(DEFAULT / 'evaluation.parquet') == summary['evaluation_sha256']
    points = pd.read_csv(DEFAULT / 'points.csv', dtype={'station': str, 'asos_station': str})
    weather = pd.read_csv(ROOT / plan['screen'] / 'asos_history_screen.csv', dtype={'asos_station': str})
    days = pd.read_csv(DEFAULT / 'daily_metrics.csv', dtype={'station': str})
    days = days.loc[days.min_slots.eq(144)].copy()
    base = days.loc[days.candidate.eq('asos_zero')].set_index(['station', 'date_kst'])
    coordinates = []
    for row in points.itertuples():
        observed = frame.loc[frame.station.eq(row.station), ['lat', 'lon']].dropna().drop_duplicates()
        assert len(observed) == 1
        actual = observed.iloc[0]
        ref = weather.loc[weather.asos_station.eq(row.asos_station)]
        assert len(ref) == 1
        coordinates.append(dict(station=row.station, catalog_to_response_km=float(distances(row.lat, row.lon, observed)[0]),
            original_asos_distance_km=row.asos_distance_km,
            response_to_frozen_asos_km=float(distances(actual.lat, actual.lon, ref)[0]),
            historical_location_or_metadata_error_resolved=False))
    rows = []
    good = frame.ice.isin([0, 1]) & frame[plan['candidate_names']].notna().all(axis=1)
    for candidate in plan['candidate_names']:
        d = days.loc[days.candidate.eq(candidate)].set_index(['station', 'date_kst']).reindex(base.index)
        assert np.array_equal(d.valid_slots, base.valid_slots)
        fixed = d.f1.fillna(0).where(base.f1.notna())
        calendar_f1 = float(fixed.groupby(level='station').mean().reindex(plan['new_stations']).fillna(0).mean())
        suppressed = good & frame.asos_zero.eq(1) & frame[candidate].eq(0)
        assert not (good & frame.asos_zero.eq(0) & frame[candidate].eq(1)).any()
        r = summary['reports'][candidate]['144']
        b = summary['reports']['asos_zero']['144']
        station_differences = {s: r['station_f1_fixed'][s] - b['station_f1_fixed'][s] for s in plan['new_stations']}
        rows.append(dict(candidate=candidate, fixed_baseline_active_calendar_f1=calendar_f1,
            baseline_active_days=int(base.f1.notna().sum()), candidate_active_days=int(d.f1.notna().sum()),
            false_alarm_only_days_removed=int((base.f1.notna() & d.f1.isna() & (base.tp + base.fn).eq(0)).sum()),
            suppressed_valid_alarm_rows=int(suppressed.sum()), suppressed_positive_rows=int((suppressed & frame.ice.eq(1)).sum()),
            suppressed_negative_rows=int((suppressed & frame.ice.eq(0)).sum()),
            station_f1_differences=station_differences,
            overall_f1_difference=sum(station_differences.values()) / 4))
    events = pd.read_csv(DEFAULT / 'logit_day_anchor1_events.csv', dtype={'station': str})
    observed = frame._merge.eq('both')
    quality = []
    for path in sorted((DEFAULT / 'response_quality').glob('*.json')):
        receipt = read(path)
        if 'conflicts' in receipt:
            quality.extend(receipt['conflicts'])
    out.mkdir(parents=True)
    pd.DataFrame(coordinates).to_csv(out / 'coordinate_diagnosis.csv', index=False)
    write(out / 'summary.json', dict(status='post_assessment_diagnosis_no_retuning', at_utc=now(),
        coordinate_diagnosis=coordinates, candidate_diagnosis=rows,
        planned_rows=len(frame), missing_observation_rows=int((~observed).sum()),
        invalid_state_observation_rows=int((observed & ~frame.ice.isin([0, 1])).sum()),
        valid_label_rows=int(good.sum()), positive_rows=int((good & frame.ice.eq(1)).sum()),
        positive_prevalence=float(frame.loc[good, 'ice'].mean()),
        diagnostic_metric_does_not_replace_primary=True, original_sites_predictions_and_summary_unchanged=True,
        summary_sha256=summary_sha, evaluation_sha256=sha(DEFAULT / 'evaluation.parquet'),
        daily_metrics_sha256=sha(DEFAULT / 'daily_metrics.csv'),
        weather_metadata_sha256=sha(ROOT / plan['screen'] / 'asos_history_screen.csv'),
        code_sha256=sha(Path(__file__))))
    assert sha(DEFAULT / 'summary.json') == summary_sha
    verify(DEFAULT)
    print((out / 'summary.json').read_text(encoding='utf-8'), flush=True)


if __name__ == '__main__':
    main()
