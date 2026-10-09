"""관측 가능한 6–72시간 수분·냉각 이력. 빈 구간을 건조·고온으로 채우지 않는다."""
import numpy as np
import pandas as pd

MEMORY_FEATURES = ["rain15_max_6h", "rain15_max_24h", "rain15_max_72h",
                   "wet_fraction_24h", "wet_fraction_72h", "rain_coverage_24h", "rain_coverage_72h",
                   "air_min_24h", "air_max_24h", "freezing_fraction_24h", "air_coverage_24h",
                   "humidity_max_24h", "dewpoint_gap_min_24h", "last_wet_age_72h", "wet_and_cold_24h"]


def moisture_memory(source):
    frames = []
    for station, part in source.groupby("station", sort=False):
        part = part.sort_values("source_time").copy()
        if part.source_time.duplicated().any():
            raise ValueError("Duplicate AWS station/time")
        time = pd.to_datetime(part.source_time)
        if ((time.dt.minute % 10 != 0) | time.dt.second.ne(0)).any():
            raise ValueError("Expected ten-minute AWS grid")
        part["wet"] = part.rain_15m.gt(0).where(part.rain_15m.notna()).astype(float)
        part["freezing"] = part.air_temp.le(0).where(part.air_temp.notna()).astype(float)
        part["dew_gap"] = part.air_temp - part.dewpoint
        indexed = part.set_index("source_time")
        result = part[["station", "source_time"]].copy()
        for hours in [6, 24, 72]:
            # (t-h,t]는 정규 10분 관측에서 정확히 6*h개 시점이다.
            window = indexed.rolling(f"{hours}h", closed="right", min_periods=1)
            result[f"rain15_max_{hours}h"] = window.rain_15m.max().to_numpy()
            if hours in [24, 72]:
                result[f"wet_fraction_{hours}h"] = window.wet.mean().to_numpy()
                result[f"rain_coverage_{hours}h"] = (window.rain_15m.count() / (6 * hours)).to_numpy()
            if hours == 24:
                result["air_min_24h"] = window.air_temp.min().to_numpy()
                result["air_max_24h"] = window.air_temp.max().to_numpy()
                result["freezing_fraction_24h"] = window.freezing.mean().to_numpy()
                result["air_coverage_24h"] = (window.air_temp.count() / 144).to_numpy()
                result["humidity_max_24h"] = window.humidity.max().to_numpy()
                result["dewpoint_gap_min_24h"] = window.dew_gap.min().to_numpy()
        last_wet = time.where(part.rain_15m.gt(0)).ffill()
        age = (time - last_wet).dt.total_seconds() / 3600
        result["last_wet_age_72h"] = age.where(age.le(72))
        known = result.rain15_max_24h.notna() & part.air_temp.notna()
        result["wet_and_cold_24h"] = (result.rain15_max_24h.gt(0) & part.air_temp.le(0)).where(known).astype(float)
        frames.append(result[["station", "source_time", *MEMORY_FEATURES]])
    return pd.concat(frames, ignore_index=True)
