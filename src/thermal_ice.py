"""사전 고정한 저온·수분 개발 기준. 공식 Ice 확률이나 운영 경보가 아니다."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.validation import canonical_station_id, normalize_state, PROTECTED_STATIONS

MOISTURE_COLUMNS = ('aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm')
POLICIES = ('baseline_ice', 'ridge_cold', 'hgb_cold', 'hgb_cold_moisture')


def validate_development(frame):
    """이미 개봉한 다음 겨울·보호 정답과 중복/비정규 시각을 거부한다."""
    if frame.empty:
        raise ValueError('Empty development population')
    stations = frame.station.map(canonical_station_id)
    if stations.isin(PROTECTED_STATIONS | {'<missing>'}).any():
        raise ValueError('Protected or missing station')
    times = pd.to_datetime(frame.time, errors='raise')
    if times.dt.tz is not None:
        times = times.dt.tz_convert('Asia/Seoul').dt.tz_localize(None)
    if times.isna().any() or not times.ge('2024-11-01').all() or not times.lt('2025-03-01').all():
        raise ValueError('Only first-winter development outcomes allowed')
    if (times.dt.minute.mod(10).ne(0) | times.dt.second.ne(0) | times.dt.microsecond.ne(0)
            | times.dt.nanosecond.ne(0)).any():
        raise ValueError('Not an exact ten-minute KST slot')
    normalized = frame.copy()
    normalized['station'] = stations
    normalized['time'] = times
    if normalized.duplicated(['station', 'time']).any():
        raise ValueError('Duplicate canonical station/time')
    return normalized


def fixed_thermal_rule(temperature, moisture, baseline, require_moisture=False):
    """목표 실측값을 읽지 않는다. 세 수분 입력 모두 없으면 기존 판정으로 복귀한다."""
    t = np.asarray(temperature, dtype=float)
    b = np.asarray(baseline, dtype=float)
    if t.ndim != 1 or b.shape != t.shape or len(moisture) != len(t):
        raise ValueError('Different prediction populations')
    if not np.isin(b, [0, 1]).all():
        raise ValueError('Baseline must provide a binary prediction for every row')
    fallback = ~np.isfinite(t)
    evidence = np.zeros(len(t), dtype=bool)
    p = (t <= 0).astype(int)
    if require_moisture:
        water = moisture.loc[:, MOISTURE_COLUMNS].to_numpy(dtype=float)
        if np.isinf(water).any():
            raise ValueError('Infinite moisture input; clean official sentinels first')
        evidence = ((water[:, 0] >= t) | (water[:, 1] > 0) | (water[:, 2] > 0))
        fallback |= np.isnan(water).all(axis=1)
        p &= evidence
    p[fallback] = b[fallback].astype(int)
    return p, fallback, evidence


def confusion(observed, predicted):
    y = np.asarray(observed, dtype=float)
    p = np.asarray(predicted, dtype=float)
    if y.shape != p.shape or not np.isin(p, [0, 1]).all():
        raise ValueError('Incomplete or mismatched predictions')
    if not (np.isnan(y) | np.isin(y, [0, 1])).all():
        raise ValueError('Invalid binary labels')
    valid = np.isfinite(y)
    y, p = y[valid], p[valid]
    tp = int(((y == 1) & (p == 1)).sum())
    fp = int(((y == 0) & (p == 1)).sum())
    fn = int(((y == 1) & (p == 0)).sum())
    tn = int(((y == 0) & (p == 0)).sum())
    return dict(n=len(y), tp=tp, fp=fp, fn=fn, tn=tn,
                precision=tp / (tp + fp) if tp + fp else None,
                recall=tp / (tp + fn) if tp + fn else None,
                f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                fpr=fp / (fp + tn) if fp + tn else None)


def _mean(values):
    values = pd.Series(values, dtype=float).dropna()
    return float(values.mean()) if len(values) else None


def diagnostic_report(frame, predicted):
    """전체 유효행, 완전일, 고정된 실제 결빙일과 사건을 함께 보고한다."""
    data = validate_development(frame[['station', 'time', 'ice']])
    data['p'] = np.asarray(predicted)
    pooled = confusion(data.ice, data.p)
    stations = pd.DataFrame([dict(station=st, **confusion(d.ice, d.p))
                             for st, d in data.groupby('station')])
    days = []
    for (st, date), part in data.groupby(['station', data.time.dt.normalize()]):
        if part.ice.notna().sum() == 144:
            days.append(dict(station=st, date=str(date.date()), **confusion(part.ice, part.p)))
    daily = pd.DataFrame(days, columns=['station', 'date', *pooled.keys()])
    ice_days = daily.loc[(daily.tp + daily.fn) > 0]
    events = []
    for station, part in data.groupby('station'):
        part = part.sort_values('time')
        positive = part.ice.eq(1)
        contiguous = part.time.diff().eq(pd.Timedelta(minutes=10))
        starts = positive & ~(positive.shift(fill_value=False) & contiguous)
        for _, event in part[positive].groupby(starts.cumsum()[positive]):
            events.append(dict(station=station, start_kst=str(event.time.min()),
                               slots=len(event), detected_slots=int(event.p.sum())))
    event_frame = pd.DataFrame(events, columns=['station', 'start_kst', 'slots', 'detected_slots'])
    pooled.update(
        fixed_station_f1_zero_undefined=float(stations.f1.fillna(0).mean()),
        fixed_ice_day_f1=_mean(ice_days.groupby('station').f1.mean()),
        fixed_ice_days=len(ice_days), fixed_ice_day_stations=ice_days.station.nunique(),
        complete_days=len(daily),
        false_alarm_nonice_days=int(((daily.tp + daily.fn == 0) & (daily.fp > 0)).sum()),
        provisional_daily_station_f1=_mean(daily.groupby('station').f1.mean()),
        events=len(event_frame), detected_events=int(event_frame.detected_slots.gt(0).sum()),
        single_slot_events=int(event_frame.slots.eq(1).sum()),
        detected_single_slot_events=int((event_frame.slots.eq(1) & event_frame.detected_slots.gt(0)).sum()))
    return pooled, stations, daily, event_frame


def evaluate_fixed_policies(frame):
    """완료된 개발 예측을 재집계한다. 후보 선택·재학습·임계값 탐색은 하지 않는다."""
    data = validate_development(frame)
    expected = data.state_raw.map(normalize_state).astype(float)
    if not np.array_equal(expected, data.ice.to_numpy(dtype=float), equal_nan=True):
        raise ValueError('Labels disagree with official 04-only definition')
    fallback_counts = {}
    for policy, column, wet in [('ridge_cold', 'baseline_weather', False),
                                 ('hgb_cold', 'selected_weather', False),
                                 ('hgb_cold_moisture', 'selected_weather', True)]:
        data[policy], fallback, _ = fixed_thermal_rule(data[column], data, data.baseline_ice, wet)
        fallback_counts[policy] = int(fallback.sum())
    metrics, station_rows, day_rows, event_rows = {}, [], [], []
    for policy in POLICIES:
        metrics[policy], stations, days, events = diagnostic_report(data, data[policy])
        for rows, result in [(station_rows, stations), (day_rows, days), (event_rows, events)]:
            result['policy'] = policy
            rows.append(result)
    return metrics, fallback_counts, pd.concat(station_rows), pd.concat(day_rows), pd.concat(event_rows)
