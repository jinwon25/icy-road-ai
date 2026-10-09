"""추가 관측의 표본 편중·시각 공백·상태/온도 관계를 정답 변경 없이 진단한다."""
import numpy as np
import pandas as pd

from src.validation import assert_training_stations, normalize_state


def quality_tables(frame, plan):
    required = {'station', 'time', 'ice', 'state_raw', 'road_temp'}
    if not required <= set(frame) or frame.duplicated(['station', 'time']).any():
        raise ValueError('Unique audited station/time outcomes required')
    frame = frame.copy(); frame['time'] = pd.to_datetime(frame.time)
    assert_training_stations(frame.station.unique())
    if frame.time.isna().any() or ((frame.time.dt.minute % 10 != 0) | frame.time.dt.second.ne(0) | frame.time.dt.microsecond.ne(0)).any():
        raise ValueError('Exact ten-minute observations required')
    first = pd.Timestamp(plan['development_start_kst']); after = pd.Timestamp(plan['development_end_kst']) + pd.Timedelta(days=1)
    if not frame.time.ge(first).all() or not frame.time.lt(after).all():
        raise ValueError('Only first-winter development outcomes permitted')
    expected_state = frame.state_raw.map(normalize_state).astype(float)
    if not np.array_equal(expected_state.to_numpy(), frame.ice.to_numpy(), equal_nan=True):
        raise ValueError('Official state semantics were changed')
    dates = pd.date_range(first, after - pd.Timedelta(days=1), freq='D')
    grid = len(dates) * 144
    station_records, episodes, daily = [], [], []
    for station, part in frame.groupby('station', sort=True):
        part = part.sort_values('time').reset_index(drop=True)
        ice = part.ice.eq(1); valid = part.ice.notna(); warm = part.road_temp.gt(2) & ice
        stats = part.loc[ice, 'road_temp'].dropna()
        contiguous = part.time.diff().eq(pd.Timedelta(minutes=10))
        starts = ice & ~(ice.shift(fill_value=False) & contiguous)
        episode_ids = starts.cumsum()
        for _, run in part.loc[ice].groupby(episode_ids.loc[ice]):
            episodes.append({'station': station, 'first_time_kst': run.time.iloc[0], 'last_time_kst': run.time.iloc[-1],
                             'observed_consecutive_slots': len(run), 'temperature_min_c': run.road_temp.min(),
                             'temperature_max_c': run.road_temp.max(), 'temperature_above_2c_slots': int(run.road_temp.gt(2).sum())})
        station_records.append({'station': station, 'observed_rows': len(part), 'planned_rows_full_winter': grid,
            'valid_state_rows': int(valid.sum()), 'undefined_state_rows': int((~valid).sum()), 'ice_rows': int(ice.sum()),
            'ice_days_observed': int(part.loc[ice, 'time'].dt.normalize().nunique()), 'ice_runs': int(starts.sum()),
            'ice_fraction_of_valid_rows': float(ice.sum()/valid.sum()) if valid.sum() else None,
            'ice_temperature_valid_rows': len(stats), 'ice_temperature_min_c': float(stats.min()) if len(stats) else None,
            'ice_temperature_median_c': float(stats.median()) if len(stats) else None,
            'ice_temperature_max_c': float(stats.max()) if len(stats) else None,
            'ice_temperature_above_zero_rows': int((part.road_temp.gt(0) & ice).sum()),
            'ice_temperature_above_2c_rows': int(warm.sum()),
            'first_observation_kst': part.time.iloc[0], 'last_observation_kst': part.time.iloc[-1]})
        part['date_kst'] = part.time.dt.normalize()
        for date, rows in part.groupby('date_kst'):
            daily.append({'station': station, 'date_kst': date, 'observed_rows': len(rows),
                          'valid_state_rows': int(rows.ice.notna().sum()), 'ice_rows': int(rows.ice.eq(1).sum()),
                          'ice_temperature_above_2c_rows': int((rows.ice.eq(1) & rows.road_temp.gt(2)).sum())})
    table = pd.DataFrame(station_records)
    run_columns = ['station', 'first_time_kst', 'last_time_kst', 'observed_consecutive_slots',
                   'temperature_min_c', 'temperature_max_c', 'temperature_above_2c_slots']
    return table, pd.DataFrame(daily), pd.DataFrame(episodes, columns=run_columns)
