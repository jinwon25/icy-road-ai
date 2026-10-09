"""최근 냉각·수증기 침적·영도 교차의 과거 전용 참조 입력.

Yi & Seo (2026), arXiv:2609.33528 및 MIT 공개 R 코드의 개념을
10분 관측·미관측 위치 추정에 맞춰 별도로 구현한다. 논문 성능 재현은 아니다.
"""
import numpy as np
import pandas as pd

from src.physical_features import ThermalContext
from src.validation import assert_training_stations
from src.weather_features import prior_join

TAUS = (20, 60)
DOSE_FEATURES = [f"near_{kind}_{tau}m" for tau in TAUS
                 for kind in ("cold_dose", "deposition_dose", "freeze_thaw", "cold_coverage", "deposition_coverage")]


def frost_point(temperature, humidity):
    """수면 포화증기압을 빙면 포화증기압으로 환산한 서리점 근사(°C)."""
    ta = np.asarray(temperature, dtype=float)
    rh = np.asarray(humidity, dtype=float)
    valid = np.isfinite(ta) & np.isfinite(rh) & (rh > 0) & (rh <= 100)
    vapor_log = np.log(np.where(valid, rh / 100, np.nan)) + 17.62 * ta / (243.12 + ta)
    return 272.62 * vapor_log / (22.46 - vapor_log)


def integrate_dose(time, road_temp, fp, tau):
    """정확한 구간 상수 입력 적분과 유효 관측 가중 커버리지.

    현재 관측을 직전10분의 대표값으로 사용하는 분석자 근사다. 10분보다 긴
    빈 간격에는 입력을 넣지 않는다. 결측을0도로 대체하지 않고 커버리지80%
    미만의 누적값은 NaN으로 둔다. 영도 교차는 결측·시간 공백에서 연결하지 않는다.
    """
    if tau <= 0:
        raise ValueError("Positive decay time required")
    time = pd.DatetimeIndex(time)
    if time.hasnans or not time.is_monotonic_increasing or time.has_duplicates:
        raise ValueError("Unique increasing timestamps required")
    road = np.asarray(road_temp, dtype=float)
    fp = np.asarray(fp, dtype=float)
    if len(time) != len(road) or len(road) != len(fp):
        raise ValueError("Input lengths differ")
    output = np.full((len(time), 5), np.nan)
    cold = deposition = crossings = cc = dc = 0.
    previous_sign = None
    for i in range(len(time)):
        dt = 0. if i == 0 else (time[i] - time[i-1]).total_seconds() / 60
        decay = np.exp(-dt / tau)
        cold *= decay; deposition *= decay; crossings *= decay; cc *= decay; dc *= decay
        contiguous = dt == 10
        weight = -tau * np.expm1(-dt / tau)
        known_road = np.isfinite(road[i])
        known_dep = known_road and np.isfinite(fp[i])
        if contiguous and known_road:
            cold += weight * max(0., -road[i])
            cc += weight / tau
            sign = np.sign(road[i])
            if sign != 0:
                if previous_sign is not None and sign != previous_sign:
                    crossings += 1.
                previous_sign = sign
        else:
            previous_sign = None
        if contiguous and known_dep:
            deposition += weight * max(0., fp[i] - road[i])
            dc += weight / tau
        output[i] = [cold if cc >= .8 else np.nan,
                     deposition if dc >= .8 else np.nan,
                     crossings if cc >= .8 else np.nan, cc, dc]
    return output


def dose_sources(source, weather):
    assert_training_stations(source.station.unique())
    assert_training_stations(weather.station.unique())
    expected = {"station", "time", "aws_air_temp", "aws_humidity"}
    if set(weather.columns) != expected:
        raise ValueError("Only prior weather inputs accepted; no target labels")
    if weather.duplicated(["station", "time"]).any():
        raise ValueError("Duplicate weather input")
    joined = source.merge(weather, on=["station", "time"], how="left", validate="one_to_one")
    frames = []
    for _, part in joined.groupby("station", sort=False):
        part = part.sort_values("time").copy()
        fp = frost_point(part.aws_air_temp, part.aws_humidity)
        for tau in TAUS:
            values = integrate_dose(part.time, part.road_temp, fp, tau)
            for k, kind in enumerate(("cold_dose", "deposition_dose", "freeze_thaw", "cold_coverage", "deposition_coverage")):
                part[f"{kind}_{tau}m"] = values[:, k]
        frames.append(part)
    return pd.concat(frames, ignore_index=True)


class AntecedentContext(ThermalContext):
    """기준 모델의 참조 선택을 유지하며 제외 지점의 국소 관측을 쓰지 않는다."""
    def __init__(self, targets, source, metadata, weather):
        super().__init__(targets, source, metadata)
        self.dose_source = dose_sources(source, weather)
        self.dose_cache = {}

    def dose_pair(self, station, reference):
        if station == reference:
            raise ValueError("Self reference forbidden")
        key = (station, reference)
        if key not in self.dose_cache:
            columns = [c.removeprefix("near_") for c in DOSE_FEATURES]
            target = self.targets.loc[self.targets.station.eq(station)].copy()
            source = self.dose_source.loc[self.dose_source.station.eq(reference), ["time", *columns]]
            joined = prior_join(target, source.rename(columns={"time": "source_time"}), "dose", 30)
            self.dose_cache[key] = joined.set_index("time")
        return self.dose_cache[key]

    def features(self, frame, forbidden):
        base, refs = super().features(frame, forbidden)
        extra = pd.DataFrame(np.nan, index=frame.index, columns=DOSE_FEATURES)
        for station, part in frame.groupby("station", sort=False):
            reference, _ = self.reference(station, forbidden)
            if reference is None:
                continue
            if reference in set(forbidden) | {station}:
                raise AssertionError("Excluded reference selected")
            pair = self.dose_pair(station, reference)
            for column in DOSE_FEATURES:
                extra.loc[part.index, column] = part.time.map(pair["dose_" + column.removeprefix("near_")]).to_numpy()
        return pd.concat([base, extra], axis=1), refs
