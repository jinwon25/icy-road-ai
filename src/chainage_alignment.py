"""공식 점 이정의 제한적 보간과 취약구간 경계 오차 민감도 계산."""
import numpy as np
import pandas as pd


def aggregate_anchors(frame):
    """같은 좌표의 중복 시설을 한 점으로 묶어 검증 분할의 중복을 막는다."""
    grouped = frame.groupby(['longitude', 'latitude'], as_index=False).agg(
        x_m=('x_m', 'median'), km=('chainage_km', 'median'),
        km_min=('chainage_km', 'min'), km_max=('chainage_km', 'max'),
        source_rows=('source_row', lambda x: '|'.join(map(str, sorted(x)))),
        count=('source_row', 'size'), distance_m=('distance_m', 'max'))
    grouped = grouped.sort_values('x_m').reset_index(drop=True)
    assert len(grouped) >= 3 and np.all(np.diff(grouped.x_m) > 0)
    sign = int(np.sign(grouped.x_m.corr(grouped.km)))
    assert sign != 0 and np.all(sign * np.diff(grouped.km) >= 0)
    return grouped, sign


def interpolate_checked(x, anchors, max_gap_m=3000):
    """관측점 범위를 벗어나거나 기준점 간격이 큰 위치에는 값을 부여하지 않는다."""
    x = np.atleast_1d(np.asarray(x, dtype=float))
    ax = anchors.x_m.to_numpy(float)
    ay = anchors.km.to_numpy(float)
    assert len(ax) >= 2 and np.all(np.diff(ax) > 0)
    right = np.searchsorted(ax, x, side='right').clip(1, len(ax)-1)
    left = right - 1
    gap = ax[right] - ax[left]
    # 끝점 자체는 허용하되 끝점 밖으로 외삽하지 않는다.
    exact = np.isin(x, ax)
    valid = np.isfinite(x) & (x >= ax[0]) & (x <= ax[-1]) & ((gap <= max_gap_m) | exact)
    y = np.interp(x, ax, ay)
    y[~valid] = np.nan
    return y, gap, valid


def overlap_sensitivity(lo_km, hi_km, start_km, end_km, margin_m):
    """고정 이정 오차 띠에서 확실·가능 교집합 길이를 보수적으로 계산한다."""
    assert hi_km >= lo_km and end_km >= start_km and margin_m >= 0
    d = margin_m / 1000
    nominal = max(0., min(hi_km, end_km)-max(lo_km, start_km))
    # 구간 양 끝이 각각 오차 띠 안에서 이동할 수 있다고 가정한다.
    guaranteed = max(0., min(hi_km-d, end_km)-max(lo_km+d, start_km))
    possible = max(0., min(hi_km+d, end_km)-max(lo_km-d, start_km))
    return nominal, guaranteed, possible
