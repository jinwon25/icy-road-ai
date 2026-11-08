"""공간 관측망의 현재 값과 과거 이력을 결합한다. 도로 정답은 사용하지 않는다."""
import numpy as np
import pandas as pd

from src.weather_history_stable import stable_temporal_features
from src.weather_network import FIELDS
from src.weather_temporal import WINDOWS


def network_history_features(frame, network):
    """현재 포함 (t-3h,t], (t-24h,t]의 고정 10분 슬롯 통계.

    각 창을 독립 합산하므로 창보다 오래된 접두 입력이 수치 상태를 바꾸지
    않는다. 달력의 누락 행은 결측이며 관측소·겨울 사이로 이력을 넘기지 않는다.
    반환 열은 기존 기상 82개, 현재 관측망 35개, 관측망 이력 30개다.
    """
    if not frame.index.equals(pd.RangeIndex(len(frame))) or not network.index.equals(frame.index):
        raise ValueError('Aligned reset input indices required')
    expected = [f'network_{field}_{kind}' for field in FIELDS
                for kind in ('idw', 'sd', 'range', 'contrast', 'count', 'distance_km', 'effective_n')]
    if list(network) != expected or np.isinf(network.to_numpy(float)).any():
        raise ValueError('Finite-or-missing declared network feature schema required')
    _, weather_history = stable_temporal_features(frame)
    result = pd.concat([weather_history, network], axis=1)
    columns = [f'network_{field}_idw' for field in FIELDS]
    history = pd.DataFrame(index=frame.index, columns=[
        f'{column}_{kind}_{hours}h' for hours in WINDOWS for column in columns
        for kind in ('mean', 'departure', 'coverage')], dtype=float)
    step = pd.Timedelta(minutes=10).value
    for _, part in frame.groupby(['station', 'winter'], sort=True):
        order = part.sort_values('time').index.to_numpy()
        times = pd.DatetimeIndex(part.loc[order, 'time']).asi8
        # stable_temporal_features에서 중복·빈 키·10분 시각을 이미 검사했다.
        positions = ((times-times[0])//step).astype(np.int64)
        current = network.loc[order, columns].to_numpy(float)
        dense = np.full((int(positions[-1])+1, len(columns)), np.nan)
        dense[positions] = current
        good = np.isfinite(dense)
        clean = np.where(good, dense, 0.)
        for hours, minimum in WINDOWS.items():
            width = hours*6
            padded = np.vstack([np.zeros((width-1, len(columns))), clean])
            padded_good = np.vstack([np.zeros((width-1, len(columns)), dtype=bool), good])
            sums = np.lib.stride_tricks.sliding_window_view(padded, width, axis=0).sum(axis=2)[positions]
            counts = np.lib.stride_tricks.sliding_window_view(padded_good, width, axis=0).sum(axis=2)[positions]
            means = np.divide(sums, counts, out=np.full_like(sums, np.nan), where=counts >= minimum)
            for j, column in enumerate(columns):
                history.loc[order, f'{column}_mean_{hours}h'] = means[:, j]
                history.loc[order, f'{column}_departure_{hours}h'] = current[:, j]-means[:, j]
                history.loc[order, f'{column}_coverage_{hours}h'] = counts[:, j]/width
    return pd.concat([result, history], axis=1)
