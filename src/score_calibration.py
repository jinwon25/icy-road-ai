"""가중 학습·학습 양성 비율의 점수 척도와 공간 제외 보정을 분리한다."""
import hashlib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit


def adjusted_logit(probability, training_prevalence, positive_weight=20., prior_adjusted=False):
    p = np.asarray(probability, dtype=float)
    if p.ndim != 1 or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError('Invalid source probabilities')
    if not 0 < training_prevalence < 1 or not np.isfinite(positive_weight) or positive_weight <= 0:
        raise ValueError('Invalid training prior or weight')
    values = logit(np.clip(p, 1e-9, 1 - 1e-9))
    if prior_adjusted:
        values -= np.log(positive_weight) + logit(training_prevalence)
    return values


def fit_sigmoid(values, labels):
    """C=1에 해당하는 단조 로지스틱 보정. 음의 기울기로 순서를 뒤집지 않는다."""
    x, y = np.asarray(values, dtype=float), np.asarray(labels, dtype=float)
    if x.ndim != 1 or x.shape != y.shape or not np.isfinite(x).all() or not np.isin(y, [0, 1]).all():
        raise ValueError('Invalid calibration rows')
    if y.sum() < 5 or (1 - y).sum() < 5:
        raise ValueError('At least five observations from both classes required')
    def objective(ab):
        a, b = ab; z = a * x + b
        error = expit(z) - y
        return float(np.logaddexp(0, z).sum() - np.dot(y, z) + .5 * a ** 2), np.array([np.dot(error, x) + a, error.sum()])
    result = minimize(objective, [1., logit(y.mean()) - x.mean()], method='L-BFGS-B', jac=True,
                      bounds=[(0., None), (None, None)], options={'maxiter': 1000, 'ftol': 1e-12, 'gtol': 1e-6})
    if not result.success:
        raise RuntimeError('Calibration did not converge')
    return dict(slope=float(result.x[0]), intercept=float(result.x[1]), rows=len(y), positives=int(y.sum()),
                objective=float(result.fun), source_identity=hashlib.sha256(np.column_stack([x, y]).tobytes()).hexdigest())


def apply_sigmoid(calibration, values):
    if calibration['slope'] < 0:
        raise ValueError('Ranking inversion prohibited')
    return expit(calibration['slope'] * np.asarray(values) + calibration['intercept'])


def validate_calibration_origins(rows, forbidden_groups):
    """보정 학습 정답이 평가 그룹에서 오거나 생성 모델이 이를 학습하면 거부한다."""
    if rows.empty or not forbidden_groups:
        raise ValueError('Calibration partition required')
    if rows.group.isin(forbidden_groups).any():
        raise ValueError('Evaluation outcomes in calibrator')
    for row in rows[['group', 'source_forbidden_groups']].drop_duplicates('group').itertuples(index=False):
        # 모든 생성 모델 행을 아래에서도 검사한다. 대표 행만으로 안전성을 주장하지 않는다.
        if not (set(forbidden_groups) | {row.group}) <= set(row.source_forbidden_groups):
            raise ValueError('Calibrator source model used evaluation or own-group outcomes')
    if any(not (set(forbidden_groups) | {row.group}) <= set(row.source_forbidden_groups)
           for row in rows[['group', 'source_forbidden_groups']].itertuples(index=False)):
        raise ValueError('Calibrator source model used evaluation or own-group outcomes')
    if rows.duplicated(['station', 'time']).any():
        raise ValueError('Duplicate calibration observation')
