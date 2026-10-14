"""결빙점 주변 학습 오차의 비중을 높이는 사전 고정 연구 가설."""
import numpy as np


def freezing_weights(target, amplitude=4.0, sigma_celsius=2.0):
    """학습 타깃으로만 계산한다. 평균1 정규화로 전체 가중치 크기를 고정한다."""
    y = np.asarray(target, dtype=float)
    if y.ndim != 1 or not y.size or not np.isfinite(y).all():
        raise ValueError('Finite nonempty training targets required')
    if not np.isfinite([amplitude, sigma_celsius]).all() or amplitude < 0 or sigma_celsius <= 0:
        raise ValueError('Nonnegative amplitude and positive width required')
    with np.errstate(over='ignore'):
        w = 1 + amplitude * np.exp(-0.5 * np.square(y / sigma_celsius))
    return w / w.mean()


def fixed_blends(baseline, mse, mae):
    a, b, c = (np.asarray(x, dtype=float) for x in (baseline, mse, mae))
    if a.ndim != 1 or b.shape != a.shape or c.shape != a.shape:
        raise ValueError('Aligned component predictions required')
    if any(np.isinf(x).any() for x in (a, b, c)):
        raise ValueError('Infinite prediction')
    if not all(np.array_equal(np.isfinite(a), np.isfinite(x)) for x in (b, c)):
        raise ValueError('Shared finite denominator required')
    pair = (b + c) / 2
    return dict(freezing_pair=pair, blend_half=(a + pair) / 2,
                blend_quarter=0.75 * a + 0.25 * pair)
