"""첫 겨울 개발용 상태 분류와 중첩 온도 입력의 경계. 공식 평가는 아니다."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.thermal_ice import validate_development
from src.validation import normalize_state

WEATHER = ['asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_wind_speed',
           'aws_rain_15m', 'aws_dewpoint', 'aws_age_minutes', 'asos_age_minutes',
           'aws_distance_km', 'asos_distance_km', 'hour_sin', 'hour_cos', 'season_sin', 'season_cos']
FEATURES = WEATHER + ['rain15_max_3h', 'asos_snow_cm', 'estimated_weather_temp',
                      'estimated_surface_dewpoint_gap', 'estimated_surface_air_gap', 'moisture_evidence']
STATE_CLASSES = {'01': 0, '02': 1, '11': 1, '14': 1, '03': 2, '12': 3,
                 '13': 4, '15': 5, '04': 6, '10': 7}
ICE_CLASS = 6
THRESHOLDS = np.unique(np.r_[0., np.geomspace(1e-6, 1., 401), np.nextafter(1., 2.)])


def state_classes(raw):
    """정의되지 않은 코드는 제외한다. 13·15를 Ice로 재정의하지 않는다."""
    def one(value):
        if normalize_state(value) is None:
            return np.nan
        value = str(value).strip()
        if value.endswith('.0'):
            value = value[:-2]
        return STATE_CLASSES[value.zfill(2)]
    return pd.Series(raw).map(one).to_numpy(dtype=float)


def unit_blocks(frame):
    """결과값 없이 고정한 18개 단위: 대회 지점 14개와 외부 공간 그룹 4개."""
    data = validate_development(frame)
    if data.groupby('station').group.nunique().ne(1).any():
        raise ValueError('A station cannot belong to several spatial groups')
    units = {st: ('competition_' + st if g == 'competition' else g)
             for st, g in data[['station', 'group']].drop_duplicates().itertuples(index=False)}
    order = {name: i % 3 for i, name in enumerate(sorted(set(units.values())))}
    return {st: order[name] for st, name in units.items()}


def excluded_stations(frame, forbidden_groups, blocks=None, block=None):
    """외부/내부 평가 그룹과 온도 입력을 받는 단위를 회귀 학습에서 제외한다."""
    if not forbidden_groups or 'competition' in forbidden_groups:
        raise ValueError('Specify external held-out groups')
    if not set(forbidden_groups) <= set(frame.group):
        raise ValueError('Unknown held-out group')
    result = set(frame.loc[frame.group.isin(forbidden_groups), 'station'])
    if block is not None:
        if blocks is None or set(blocks) != set(frame.station):
            raise ValueError('Incomplete auxiliary fold assignment')
        result |= {st for st, b in blocks.items() if b == block}
    return result


def thermal_features(weather, temperature):
    """허용 목록만 읽는다. 목표 실측 온도·상태와 지점 ID는 입력에 넣지 않는다."""
    t = np.asarray(temperature, dtype=float)
    if t.shape != (len(weather),) or np.isinf(t).any():
        raise ValueError('Invalid estimated temperature population')
    x = weather[WEATHER + ['rain15_max_3h', 'asos_snow_cm']].copy()
    x['estimated_weather_temp'] = t
    x['estimated_surface_dewpoint_gap'] = t - x.aws_dewpoint
    x['estimated_surface_air_gap'] = t - x.aws_air_temp
    water = x[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']]
    evidence = (x.aws_dewpoint.ge(t) | x.rain15_max_3h.gt(0) | x.asos_snow_cm.gt(0)).astype(float)
    x['moisture_evidence'] = evidence.mask(water.isna().all(axis=1) | ~np.isfinite(t))
    if np.isinf(x.to_numpy(dtype=float)).any():
        raise ValueError('Infinite feature; clean sentinel first')
    return x[FEATURES]


def ice_probability(model, features, joint=False):
    """관측된 클래스 순서에 따라 Ice 열을 찾는다. 없으면 조용히 통과하지 않는다."""
    classes = np.asarray(model.classes_)
    match = np.flatnonzero(classes == (ICE_CLASS if joint else 1))
    if len(match) != 1:
        raise ValueError('Training population must contain Ice')
    p = np.asarray(model.predict_proba(features))
    if p.shape != (len(features), len(classes)) or not np.isfinite(p).all() or (p < 0).any() or not np.allclose(p.sum(axis=1), 1):
        raise ValueError('Invalid class probabilities')
    return p[:, match[0]]


def threshold_prediction(scores, threshold, fallback, baseline):
    s, f, b = np.asarray(scores), np.asarray(fallback, dtype=bool), np.asarray(baseline)
    if s.ndim != 1 or f.shape != s.shape or b.shape != s.shape or not np.isfinite(s).all() or not np.isin(b, [0, 1]).all():
        raise ValueError('Incomplete prediction population')
    return np.where(f, b, s >= threshold).astype(int)


def threshold_table(frame, scores, fallback, baseline):
    """같은 유효행·완전일·실제 결빙일을 모든 사전 고정 임계값에 사용한다."""
    frame = validate_development(frame)
    y = frame.ice.to_numpy(dtype=float)
    if not (np.isnan(y) | np.isin(y, [0, 1])).all():
        raise ValueError('Invalid official binary labels')
    valid = np.isfinite(y)
    st, _ = pd.factorize(frame.station[valid], sort=True)
    day, keys = pd.factorize(pd.MultiIndex.from_arrays([frame.station[valid], frame.time[valid].dt.normalize()]), sort=True)
    yy = y[valid].astype(int)
    st_pos = np.bincount(st, weights=yy); day_pos = np.bincount(day, weights=yy)
    ice_days = (np.bincount(day) == 144) & (day_pos > 0)
    ds, _ = pd.factorize(keys.get_level_values(0), sort=True)
    counts = np.bincount(ds[ice_days], minlength=len(st_pos)); included = counts > 0
    rows = []
    for threshold in THRESHOLDS:
        pred = threshold_prediction(scores, threshold, fallback, baseline)[valid]
        tp = int((pred * yy).sum()); fp = int(pred.sum() - tp); fn = int(yy.sum() - tp)
        st_pred = np.bincount(st, weights=pred, minlength=len(st_pos))
        st_tp = np.bincount(st, weights=pred * yy, minlength=len(st_pos))
        denom = st_pos + st_pred
        sf = np.divide(2 * st_tp, denom, out=np.zeros_like(denom), where=denom > 0)
        day_pred = np.bincount(day, weights=pred, minlength=len(day_pos))
        day_tp = np.bincount(day, weights=pred * yy, minlength=len(day_pos))
        df = np.divide(2 * day_tp, day_pos + day_pred, out=np.zeros_like(day_pos), where=(day_pos + day_pred) > 0)
        sums = np.bincount(ds[ice_days], weights=df[ice_days], minlength=len(st_pos))
        rows.append(dict(threshold=float(threshold), tp=tp, fp=fp, fn=fn,
                         f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.,
                         fixed_station_f1_zero_undefined=float(sf.mean()),
                         fixed_ice_day_f1=float((sums[included] / counts[included]).mean()) if included.any() else 0.))
    return pd.DataFrame(rows)


def select_threshold(table, baseline_fp):
    feasible = table.loc[table.fp.le(baseline_fp)]
    if feasible.empty:
        raise ValueError('No threshold meets the predeclared false-alarm budget')
    return float(feasible.sort_values(['fixed_ice_day_f1', 'f1', 'threshold'], ascending=False).iloc[0].threshold)


def eligibility(candidate, baseline, candidate_stations, baseline_stations):
    """내부 결과만으로 전체 개선과 짧은 사건·지점별 악화를 함께 심사한다."""
    c, b = candidate, baseline
    cs, bs = candidate_stations.set_index('station'), baseline_stations.set_index('station')
    if set(cs.index) != set(bs.index) or c['n'] != b['n'] or any(c[k] != b[k] for k in ['complete_days', 'fixed_ice_days', 'fixed_ice_day_stations', 'events', 'single_slot_events']):
        raise ValueError('Different comparison populations')
    if not cs.n.eq(bs.n).all() or not (cs.tp + cs.fn).eq(bs.tp + bs.fn).all():
        raise ValueError('Different station populations')
    metrics = ['f1', 'fixed_ice_day_f1', 'fixed_station_f1_zero_undefined']
    safe_f1 = all((c[k] or 0) + 1e-12 >= (b[k] or 0) for k in metrics)
    improved = any((c[k] or 0) > (b[k] or 0) + 1e-12 for k in metrics[:2])
    reliable = (bs.tp + bs.fn) >= 5
    checks = dict(f1_guards=safe_f1, strict_improvement=improved, false_alarm_budget=c['fp'] <= b['fp'],
                  single_slot_guard=c['detected_single_slot_events'] >= b['detected_single_slot_events'],
                  station_recall_guard=bool(cs.loc[reliable, 'tp'].ge(bs.loc[reliable, 'tp']).all()))
    return all(checks.values()), checks
