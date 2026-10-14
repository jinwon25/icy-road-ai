"""Q&A633의 지표별 분모를 명시한다. 부분 날짜 최소 관측 수는 여전히 잠정이다."""
import numpy as np
import pandas as pd
from src.method_blending import domain
from src.validation import canonical_station_id

METRICS = ('precision', 'recall', 'f1')


def daily_table(frame, prediction, station_population, min_slots=144,
                start='2024-11-01', end='2025-03-01'):
    if isinstance(min_slots, bool) or int(min_slots) != min_slots or not 1 <= min_slots <= 144:
        raise ValueError('Explicit provisional valid-slot threshold1–144 required')
    f = frame[['station', 'time', 'ice']].copy()
    f.station = f.station.map(canonical_station_id); f.time = pd.to_datetime(f.time); domain(f)
    pop = [canonical_station_id(s) for s in station_population]
    if not pop or len(pop) != len(set(pop)) or not set(f.station) <= set(pop):
        raise ValueError('Unique declared station population required')
    # 빈 지점의 ID까지 검증하여 보호/개봉 평가가 정적 분모에 섞이지 않게 한다.
    domain(pd.DataFrame({'station': pop, 'time': pd.Timestamp('2024-11-01')}))
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    if a.tz is not None or b.tz is not None or a != a.normalize() or b != b.normalize() or not pd.Timestamp('2024-11-01') <= a < b <= pd.Timestamp('2025-03-01'):
        raise ValueError('First winter whole KST dates required')
    if not (f.time.ge(a) & f.time.lt(b)).all(): raise ValueError('Rows outside declared calendar')
    p = np.asarray(prediction, float)
    if p.shape != (len(f),) or not np.isin(p, [0, 1]).all() or not (f.ice.isna() | f.ice.isin([0, 1])).all():
        raise ValueError('Defined binary predictions and valid-or-missing Ice labels required')
    valid = f.ice.isin([0, 1]).to_numpy(); y = f.ice.to_numpy(float)
    rows = pd.DataFrame({'station': f.station, 'date_kst': f.time.dt.normalize(), 'valid_slots': valid.astype(int),
        'tp': (valid & (y == 1) & (p == 1)).astype(int), 'fp': (valid & (y == 0) & (p == 1)).astype(int),
        'fn': (valid & (y == 1) & (p == 0)).astype(int), 'tn': (valid & (y == 0) & (p == 0)).astype(int)})
    grouped = rows.groupby(['station', 'date_kst']).sum()
    grid = pd.MultiIndex.from_product([pop, pd.date_range(a, b-pd.Timedelta(days=1), freq='D')], names=['station', 'date_kst'])
    days = grouped.reindex(grid, fill_value=0).reset_index()
    days['actual_ice_slots'] = days.tp+days.fn; days['predicted_ice_slots'] = days.tp+days.fp
    days['metric_active_slots'] = days.tp+days.fp+days.fn
    days['coverage_accepted'] = days.valid_slots.ge(min_slots)
    days['expected_slots'] = 144
    days['both_zero'] = days.metric_active_slots.eq(0)
    days['miss_only'] = days.actual_ice_slots.gt(0) & days.predicted_ice_slots.eq(0)
    days['false_alarm_only'] = days.actual_ice_slots.eq(0) & days.predicted_ice_slots.gt(0)
    denominators = {'precision': days.tp+days.fp, 'recall': days.tp+days.fn, 'f1': 2*days.tp+days.fp+days.fn}
    for metric, denom in denominators.items():
        numerator = 2*days.tp if metric == 'f1' else days.tp
        days[metric] = numerator.div(denom.where(denom.gt(0))).where(days.coverage_accepted)
        days['included_'+metric] = days[metric].notna()
    return days


def aggregate(days, station_population):
    pop = [canonical_station_id(s) for s in station_population]
    if not pop or len(pop) != len(set(pop)) or set(days.station) != set(pop) or days.duplicated(['station', 'date_kst']).any():
        raise ValueError('Full declared station/calendar table required')
    rows = []
    for station in pop:
        f = days.loc[days.station.eq(station)]; accepted = f.coverage_accepted
        record = dict(station=station, planned_days=len(f), coverage_days=int(accepted.sum()),
            active_days=int((accepted & ~f.both_zero).sum()), both_zero_days=int((accepted & f.both_zero).sum()),
            miss_only_days=int((accepted & f.miss_only).sum()), false_alarm_only_days=int((accepted & f.false_alarm_only).sum()),
            excluded_ice_days=int((~accepted & f.actual_ice_slots.gt(0)).sum()))
        for metric in METRICS:
            values = f[metric].dropna(); record[metric+'_days'] = len(values)
            record[metric] = float(values.mean()) if len(values) else None
        rows.append(record)
    stations = pd.DataFrame(rows)
    summary = dict(population_stations=len(pop), planned_days=len(days), coverage_days=int(days.coverage_accepted.sum()),
        active_days=int((days.coverage_accepted & ~days.both_zero).sum()),
        both_zero_days=int((days.coverage_accepted & days.both_zero).sum()),
        miss_only_days=int((days.coverage_accepted & days.miss_only).sum()),
        false_alarm_only_days=int((days.coverage_accepted & days.false_alarm_only).sum()),
        excluded_ice_days=int((~days.coverage_accepted & days.actual_ice_slots.gt(0)).sum()),
        confirmed_missed_day_policy=True, minimum_coverage_officially_confirmed=False,
        false_alarm_only_recall_explicitly_answered=False, official_competition_score=False)
    for metric in METRICS:
        values = stations[metric].dropna()
        summary[metric+'_days'] = int(stations[metric+'_days'].sum())
        summary[metric+'_stations'] = len(values)
        summary[metric+'_available_station_mean'] = float(values.mean()) if len(values) else None
        summary[metric+'_all_population_station_mean'] = float(values.mean()) if len(values) == len(pop) else None
    return summary, stations
