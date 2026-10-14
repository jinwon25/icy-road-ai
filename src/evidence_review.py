"""개봉된 첫 겨울 자료의 위치·지표·입력 범위를 진단한다. 모델 선택용이 아니다."""
import numpy as np
import pandas as pd

from src.temperature_transfer import validate_development
from src.validation import canonical_station_id, PROTECTED_STATIONS
from src.weather_features import haversine_km


def review_domain(frame):
    """ID를 먼저 정규화해 보호 지점·다음 겨울·중복·비정규 시각을 거부한다."""
    result = frame.copy()
    result['station'] = result.station.map(canonical_station_id)
    result['time'] = pd.to_datetime(result.time)
    if result.station.eq('<missing>').any() or set(result.station) & PROTECTED_STATIONS:
        raise ValueError('Missing or protected station')
    validate_development(result)
    return result


def coordinate_review(observations, catalog, tolerance_m=20.):
    """20m는 문서 반올림 차이 검토 기준이며 현장 위치 인증 기준이 아니다."""
    observations = review_domain(observations)
    if not np.isfinite(tolerance_m) or tolerance_m < 0:
        raise ValueError('Invalid coordinate comparison tolerance')
    catalog = catalog.copy()
    catalog['station'] = catalog.station.map(canonical_station_id)
    if catalog.station.duplicated().any():
        raise ValueError('Duplicate catalogue station')
    catalog = catalog.set_index('station')
    summaries, pairs = [], []
    for station, part in observations.groupby('station', sort=True):
        if station not in catalog.index:
            raise ValueError('Missing catalogue station')
        row = catalog.loc[station]
        if not np.isfinite([row.lat, row.lon]).all() or not (-90 <= row.lat <= 90 and -180 <= row.lon <= 180):
            raise ValueError('Invalid catalogue coordinate')
        valid = (np.isfinite(part.lat) & np.isfinite(part.lon)
                 & part.lat.between(-90, 90) & part.lon.between(-180, 180))
        distances = []
        for (lat, lon), subset in part.loc[valid].groupby(['lat', 'lon']):
            distance = 1000 * haversine_km(row.lat, row.lon, lat, lon)
            distances.append(distance)
            pairs.append(dict(station=station, response_lat=float(lat), response_lon=float(lon),
                              rows=len(subset), first_time=str(subset.time.min()),
                              last_time=str(subset.time.max()), distance_m=float(distance)))
        maximum = max(distances) if distances else None
        status = ('coordinate_unavailable' if maximum is None else
                  'catalogue_response_discrepancy' if maximum > tolerance_m else
                  'within_comparison_tolerance_location_unverified')
        summaries.append(dict(station=station, name=row['name'], catalog_lat=float(row.lat),
                              catalog_lon=float(row.lon), review_rows=len(part),
                              coordinate_rows=int(valid.sum()), missing_or_invalid_rows=int((~valid).sum()),
                              coordinate_pairs=len(distances), max_distance_m=maximum, status=status,
                              physical_location_verified=False, historical_relocation_verified=False))
    return pd.DataFrame(summaries), pd.DataFrame(pairs)


def day_counts(frame, prediction):
    """실측 없는 예정 시점은 유효 분모에 넣지 않고 비결빙으로 채우지 않는다."""
    frame = review_domain(frame)
    if not frame[prediction].isin([0, 1]).all():
        raise ValueError('Incomplete binary prediction')
    if not (frame.ice.isna() | frame.ice.isin([0, 1])).all():
        raise ValueError('Invalid Ice label')
    valid = frame.ice.isin([0, 1])
    data = pd.DataFrame({'station': frame.station, 'date': frame.time.dt.normalize(),
                         'slots': valid.astype(int), 'actual': (valid & frame.ice.eq(1)).astype(int),
                         'predicted': (valid & frame[prediction].eq(1)).astype(int),
                         'tp': (valid & frame.ice.eq(1) & frame[prediction].eq(1)).astype(int)})
    days = data.groupby(['station', 'date'], sort=True).sum().reset_index()
    days['precision'] = days.tp.div(days.predicted.where(days.predicted.gt(0)))
    days['recall'] = days.tp.div(days.actual.where(days.actual.gt(0)))
    # P/R가 모두 정의되는 날만 남기면 전부 놓친 결빙일과 오경보일이 빠진다.
    days['f1'] = (2 * days.tp).div((days.actual + days.predicted).where((days.actual + days.predicted).gt(0)))
    return days


def aggregate_days(days, min_slots, undefined_policy, station_population):
    """지표별 날짜 평균→지점 평균. 미정의 처리의 차이는 민감도로 분리한다."""
    if isinstance(min_slots, bool) or int(min_slots) != min_slots or not 1 <= min_slots <= 144:
        raise ValueError('Coverage must be an integer between 1 and 144')
    if undefined_policy not in {'metricwise_omit', 'undefined_zero', 'joint_defined_only'}:
        raise ValueError('Unknown undefined-metric policy')
    population = list(map(canonical_station_id, station_population))
    if not population or len(set(population)) != len(population) or set(days.station) - set(population):
        raise ValueError('Invalid station population')
    eligible = days.loc[days.slots.ge(min_slots)]
    active = eligible.loc[(eligible.actual + eligible.predicted).gt(0)]
    included = active.loc[active.actual.gt(0) & active.predicted.gt(0)] if undefined_policy == 'joint_defined_only' else active
    result = dict(min_valid_slots=int(min_slots), undefined_policy=undefined_policy,
                  population_stations=len(population), planned_days=len(days), coverage_days=len(eligible),
                  active_days=len(active), both_zero_days=int(((eligible.actual + eligible.predicted) == 0).sum()),
                  excluded_by_joint_days=len(active) - len(included),
                  coverage_ice_days=int(eligible.actual.gt(0).sum()),
                  excluded_by_coverage_ice_days=int(days.loc[days.slots.lt(min_slots), 'actual'].gt(0).sum()),
                  included_ice_days=int(included.actual.gt(0).sum()),
                  included_false_alarm_only_days=int((included.actual.eq(0) & included.predicted.gt(0)).sum()))
    for metric in ['precision', 'recall', 'f1']:
        values = included[metric].fillna(0.) if undefined_policy == 'undefined_zero' else included[metric]
        grouped = values.groupby(included.station).mean().reindex(population)
        result[metric + '_days'] = int(values.notna().sum())
        result[metric + '_stations'] = int(grouped.notna().sum())
        result[metric + '_available_station_macro'] = float(grouped.mean()) if grouped.notna().any() else None
        # 고정 지점의 미정의를 0으로 놓은 값도 별도 이름으로 표시한다.
        result[metric + '_fixed_station_zero_undefined'] = float(grouped.fillna(0.).mean())
    return result


def fit_feature_envelope(training, features):
    """학습 입력만으로 정한 주변 범위. AOA 구현이나 오차 보장으로 해석하지 않는다."""
    training = review_domain(training)
    if not features or {'ice', 'state_raw', 'road_temp'} & set(features) or len(set(features)) != len(features):
        raise ValueError('Outcome or duplicate feature')
    rows = []
    for feature in features:
        values = training[feature].astype(float)
        if np.isinf(values).any() or not values.notna().any():
            raise ValueError('Infinite or completely missing training feature')
        rows.append(dict(feature=feature, training_finite=int(values.notna().sum()),
                         training_missing_fraction=float(values.isna().mean()),
                         minimum=float(values.min()), maximum=float(values.max()),
                         q01=float(values.quantile(.01)), q99=float(values.quantile(.99))))
    return pd.DataFrame(rows).set_index('feature')


def feature_support(inputs, envelope):
    """범위 밖·결측은 별도 기록하며 범위 안이라는 이유로 신뢰도를 인증하지 않는다."""
    inputs = review_domain(inputs)
    features = list(envelope.index)
    summaries, details = [], []
    for station, part in inputs.groupby('station', sort=True):
        missing, outside, tails = [], [], []
        for feature in features:
            values = part[feature].astype(float)
            if np.isinf(values).any():
                raise ValueError('Infinite evaluation feature')
            bounds = envelope.loc[feature]
            absent = values.isna()
            out = values.notna() & ~values.between(bounds.minimum, bounds.maximum)
            tail = values.notna() & ~values.between(bounds.q01, bounds.q99)
            missing.append(absent.to_numpy()); outside.append(out.to_numpy()); tails.append(tail.to_numpy())
            details.append(dict(station=station, feature=feature, rows=len(part),
                                missing_fraction=float(absent.mean()), outside_range_fraction=float(out.mean()),
                                outside_q01_q99_fraction=float(tail.mean()),
                                observed_minimum=float(values.min()) if values.notna().any() else None,
                                observed_maximum=float(values.max()) if values.notna().any() else None))
        summaries.append(dict(station=station, rows=len(part),
                              any_missing_fraction=float(np.any(missing, axis=0).mean()),
                              any_outside_training_range_fraction=float(np.any(outside, axis=0).mean()),
                              any_outside_q01_q99_fraction=float(np.any(tails, axis=0).mean()),
                              predictive_reliability_verified=False))
    return pd.DataFrame(summaries), pd.DataFrame(details)
