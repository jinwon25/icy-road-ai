"""가중치를 추정하지 않는 두 기상 온도 예측의 동일 비중 평균."""
import numpy as np

CANDIDATE = 'equal_mean_weather14_weather12'
COMPONENTS = ('direct_weather14', 'weather12_no_distance')


def equal_mean(first, second):
    first, second = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    if first.ndim != 1 or first.shape != second.shape:
        raise ValueError('Aligned one-dimensional component predictions required')
    if np.isinf(first).any() or np.isinf(second).any():
        raise ValueError('Infinite component prediction')
    if not np.array_equal(np.isfinite(first), np.isfinite(second)):
        raise ValueError('Component valid-row denominator differs')
    # 큰 유한 값도 덧셈 전 절반으로 줄여 불필요한 overflow를 피한다.
    return .5 * first + .5 * second


def component_error_diagnostics(frame, first, second):
    """이미 개봉된 개발 정답의 오차 상관·공분산. 선택 가중치로 쓰지 않는다."""
    prediction = equal_mean(first, second)
    y = frame.road_temp.to_numpy(dtype=float)
    mask = np.isfinite(y) & np.isfinite(prediction)
    a = np.asarray(first)[mask] - y[mask]; b = np.asarray(second)[mask] - y[mask]
    if not len(a):
        return {'n': 0, 'error_correlation': None, 'mean_error_product': None, 'mixture_mse': None}
    correlation = float(np.corrcoef(a, b)[0, 1]) if len(a) > 1 and np.std(a) > 0 and np.std(b) > 0 else None
    return dict(n=int(mask.sum()), error_correlation=correlation,
                mean_error_product=float(np.mean(a*b)),
                mixture_mse=float(np.mean((.5*a+.5*b)**2)),
                mse_identity=.25*float(np.mean(a*a)) + .25*float(np.mean(b*b)) + .5*float(np.mean(a*b)))
