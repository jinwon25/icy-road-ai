"""다른 개발 지점의 과거 노면상태와 관측 커버리지 입력."""
import numpy as np
import pandas as pd
from src.physical_features import ThermalContext
from src.validation import assert_training_stations, normalize_state
from src.weather_features import prior_join

VALID_CODES = (1, 2, 3, 4, 10, 11, 12, 13, 14, 15)
SOURCE_FEATURES = [f"code_{code:02d}" for code in VALID_CODES]
SOURCE_FEATURES += [f"{kind}_fraction_{minutes}m" for minutes in (60, 180)
                    for kind in ("water", "ice", "snow", "deicing", "uncertain")]
SOURCE_FEATURES += ["coverage_60m", "coverage_180m", "last_ice_age_360m"]
STATE_FEATURES = ["near_state_" + c for c in SOURCE_FEATURES]


def state_history(source):
    if set(source.columns) != {"station", "time", "state_raw"}:
        raise ValueError("Only development source station/time/state accepted")
    assert_training_stations(source.station.unique())
    frames = []
    for station, part in source.groupby("station", sort=False):
        part = part.sort_values("time").copy()
        part["time"] = pd.to_datetime(part.time).astype("datetime64[ns]")
        if part.time.isna().any() or part.time.duplicated().any():
            raise ValueError("Invalid source timestamps")
        if ((part.time.dt.minute % 10 != 0) | part.time.dt.second.ne(0)).any():
            raise ValueError("Expected ten-minute source grid")
        valid = part.state_raw.map(normalize_state).notna()
        code = pd.to_numeric(part.state_raw, errors="coerce").where(valid)
        indexed = pd.DataFrame(index=pd.DatetimeIndex(part.time))
        indexed["valid"] = valid.astype(float).to_numpy()
        groups = {"water": [2, 11, 14], "ice": [4], "snow": [3], "deicing": [12, 13], "uncertain": [15]}
        for kind, codes in groups.items():
            indexed[kind] = code.isin(codes).where(valid).astype(float).to_numpy()
        result = part[["station", "time"]].copy()
        for current in VALID_CODES:
            result[f"code_{current:02d}"] = code.eq(current).where(valid).astype(float)
        for minutes in (60, 180):
            # (t-window,t]에서 미정의·비관측을 음성이나 건조로 채우지 않는다.
            window = indexed.rolling(f"{minutes}min", closed="right", min_periods=1)
            coverage = window.valid.sum().to_numpy() / (minutes / 10)
            result[f"coverage_{minutes}m"] = coverage
            for kind in groups:
                fraction = window[kind].mean().to_numpy()
                result[f"{kind}_fraction_{minutes}m"] = np.where(coverage >= .8, fraction, np.nan)
        last_ice = part.time.where(code.eq(4)).ffill()
        age = (part.time - last_ice).dt.total_seconds() / 60
        result["last_ice_age_360m"] = age.where(age.le(360))
        frames.append(result[["station", "time", *SOURCE_FEATURES]])
    return pd.concat(frames, ignore_index=True)


class SurfaceStateContext(ThermalContext):
    def __init__(self, targets, thermal_source, metadata, state_source):
        super().__init__(targets, thermal_source, metadata)
        self.state_source = state_history(state_source)
        self.state_cache = {}

    def state_pair(self, target, reference):
        if target == reference:
            raise ValueError("Self reference forbidden")
        key = (target, reference)
        if key not in self.state_cache:
            query = self.targets.loc[self.targets.station.eq(target)].copy()
            source = self.state_source.loc[self.state_source.station.eq(reference), ["time", *SOURCE_FEATURES]]
            self.state_cache[key] = prior_join(query, source.rename(columns={"time": "source_time"}), "state", 30).set_index("time")
        return self.state_cache[key]

    def features(self, frame, forbidden):
        base, refs = super().features(frame, forbidden)
        extra = pd.DataFrame(np.nan, index=frame.index, columns=STATE_FEATURES)
        for target, part in frame.groupby("station", sort=False):
            reference, _ = self.reference(target, forbidden)
            if reference is None:
                continue
            if reference in set(forbidden) | {target}:
                raise AssertionError("Excluded reference selected")
            joined = self.state_pair(target, reference)
            for column, source_column in zip(STATE_FEATURES, SOURCE_FEATURES):
                extra.loc[part.index, column] = part.time.map(joined["state_" + source_column]).to_numpy()
            age = part.time.map(joined.state_age_minutes)
            if not age.dropna().between(0, 30, inclusive="right").all():
                raise AssertionError("Future or stale state reference")
        return pd.concat([base, extra], axis=1), refs
