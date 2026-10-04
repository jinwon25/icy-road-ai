"""Strictly prior RWIS context with fold-wide reference exclusion."""
import numpy as np
import pandas as pd

from src.validation import assert_training_stations, canonical_station_id
from src.weather_features import haversine_km, prior_join


def add_source_history(source):
    """Do not difference daily rain across midnight, gaps, or negative resets."""
    frames = []
    assert_training_stations(source.station.unique())
    for _, part in source.groupby('station'):
        part = part.sort_values('time').copy()
        if part.time.duplicated().any():
            raise ValueError('Duplicate RWIS source time')
        consecutive = part.time.diff().eq(pd.Timedelta(minutes=10))
        same_day = part.time.dt.normalize().eq(part.time.shift().dt.normalize())
        rain_delta = part.rain_cum.diff()
        part['rain_10m'] = rain_delta.where(consecutive & same_day & rain_delta.ge(0))
        window = part.set_index('time').ice.rolling('60min', closed='both', min_periods=1)
        part['ice_seen_60m'] = window.max().to_numpy()
        part['ice_history_count'] = window.count().to_numpy()
        frames.append(part)
    return pd.concat(frames, ignore_index=True)


def select_reference(metadata, target_id, excluded, moisture=False):
    """Metadata only: closest same-route allowed station, with no target reference."""
    assert_training_stations(metadata.index)
    target_id = canonical_station_id(target_id)
    forbidden = {canonical_station_id(s) for s in excluded} | {target_id}
    row = metadata.loc[target_id]
    candidates = metadata.loc[metadata.route.eq(row.route) & ~metadata.index.isin(forbidden)]
    if moisture:
        candidates = candidates.loc[candidates.has_moisture]
    if candidates.empty:
        return None, np.nan
    distances = {sid: haversine_km(row.lat, row.lon, item.lat, item.lon)
                 for sid, item in candidates.iterrows()}
    sid = min(distances, key=lambda s: (distances[s], s))
    return sid, distances[sid]


def pair_context(target, source, prefix):
    assert_training_stations(target.station.unique())
    assert_training_stations(source.station.unique())
    if len(set(target.station)) != 1 or len(set(source.station)) != 1:
        raise ValueError('Pair context needs one target and one source')
    if set(target.station.map(canonical_station_id)) & set(source.station.map(canonical_station_id)):
        raise ValueError('A target cannot reference its own RWIS')
    columns = ['time', 'ice', 'road_temp', 'humidity', 'rain_10m', 'ice_seen_60m', 'ice_history_count']
    return prior_join(target, source[columns].rename(columns={'time': 'source_time'}), prefix, 30)
