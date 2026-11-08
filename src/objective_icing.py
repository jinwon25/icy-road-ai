"""기상 기반 제한 보정의 손실 대조. 정답은 학습 손실에만 전달한다."""
import numpy as np
import pandas as pd
import torch
from torch.nn import functional as F

from src.anchored_icing import linear_features
from src.synoptic_icing import sample_weights

HINGES = {'asos_air_temp': [-5., 0., 5.], 'asos_ground_temp': [-5., 0., 5.],
          'asos_humidity': [80., 95.], 'dewpoint_depression': [0., 3.]}


def features(frame):
    x = linear_features(frame)
    for column, knots in HINGES.items():
        for knot in knots:
            x[column + '_above_' + str(knot)] = (x[column] - knot).clip(lower=0)
    return x


def fit_preprocessor(x):
    a = np.asarray(x, float)
    if a.ndim != 2 or np.isinf(a).any():
        raise ValueError('Finite or missing feature matrix required')
    medians = np.array([np.median(c[np.isfinite(c)]) if np.isfinite(c).any() else 0. for c in a.T])
    filled = np.where(np.isnan(a), medians, a)
    means, scales = filled.mean(axis=0), filled.std(axis=0)
    scales[scales < 1e-8] = 1.
    return {'medians': medians, 'means': means, 'scales': scales}


def transform(x, state):
    a = np.asarray(x, float)
    if a.ndim != 2 or a.shape[1] != len(state['medians']) or np.isinf(a).any():
        raise ValueError('Aligned finite or missing features required')
    missing = np.isnan(a)
    z = (np.where(missing, state['medians'], a) - state['means']) / state['scales']
    return np.concatenate([np.clip(z, -8., 8.), missing.astype(float)], axis=1).astype(np.float32)


def group_data(frame):
    """완전한 날짜의 양성 그룹만 soft loss에 사용하며 BCE는 모든 학습행에 적용."""
    if frame.empty or not frame.ice.isin([0, 1]).all() or frame.duplicated(['station','time']).any():
        raise ValueError('Unique binary training observations required')
    f = frame.reset_index(drop=True)
    ids, keys = pd.factorize(pd.MultiIndex.from_arrays([f.station, f.winter]), sort=True)
    days, daykeys = pd.factorize(pd.MultiIndex.from_arrays([f.station, f.winter, f.time.dt.normalize()]), sort=True)
    n = np.bincount(days)
    positives = np.bincount(days, weights=f.ice)
    positive_days = (n == 144) & (positives > 0)
    day_stations = np.array([keys.get_loc((s, y)) for s, y, _ in daykeys])
    counts = np.bincount(day_stations[positive_days], minlength=len(keys))
    day_weights = np.zeros(len(daykeys))
    if positive_days.any():
        day_weights[positive_days] = 1 / counts[day_stations[positive_days]] / np.count_nonzero(counts)
    station_weights = (np.bincount(ids, weights=f.ice, minlength=len(keys)) > 0).astype(float)
    if station_weights.sum():
        station_weights /= station_weights.sum()
    return {'station_ids': ids, 'day_ids': days, 'station_weights': station_weights,
            'day_weights': day_weights, 'row_weights': sample_weights(f, 'day')}


def soft_loss(probability, target, ids, weights):
    tp = torch.zeros_like(weights).scatter_add(0, ids, probability * target)
    den = torch.zeros_like(weights).scatter_add(0, ids, probability + target)
    return torch.sum(weights * (1 - 2 * tp / den.clamp_min(1e-8)))


def data_loss(logits, target, grouped, kind):
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction='none')
    w = grouped['row_weights']
    ordinary = (w * bce).mean()
    if kind == 'bce_day':
        return ordinary
    p = torch.sigmoid(logits)
    if kind == 'focal_day':
        pt = p * target + (1-p) * (1-target)
        return (w * (1-pt).square() * bce).mean()
    if kind not in ('soft_station', 'soft_day'):
        raise ValueError('Unknown planned loss')
    level = 'station' if kind == 'soft_station' else 'day'
    return .5 * ordinary + .5 * soft_loss(p, target, grouped[level+'_ids'], grouped[level+'_weights'])


def fit(frame, kind, settings):
    x = features(frame)
    preprocessing = fit_preprocessor(x)
    full = transform(x, preprocessing)
    # 동일 입력을 한 번 계산하고 역색인으로 원래 행 손실을 정확히 복원한다.
    unique, inverse = np.unique(full, axis=0, return_inverse=True)
    z = torch.from_numpy(unique)
    ix = torch.from_numpy(inverse)
    y = torch.tensor(frame.ice.to_numpy(), dtype=torch.float32)
    air = torch.tensor(frame.asos_air_temp.to_numpy(), dtype=torch.float32)
    if not torch.isfinite(air).all():
        raise ValueError('Finite air temperature required for training')
    grouped = {key: torch.tensor(value, dtype=torch.long if key.endswith('_ids') else torch.float32)
               for key, value in group_data(frame).items()}
    coefficient = torch.zeros(z.shape[1], requires_grad=True)
    intercept = torch.zeros((), requires_grad=True)
    optimizer = torch.optim.Adam([coefficient, intercept], lr=settings['learning_rate'])
    history = []
    for step in range(settings['steps']):
        optimizer.zero_grad()
        delta = settings['cap_c'] * torch.tanh(z @ coefficient + intercept)
        logits = (delta[ix] - air) / 2
        loss = data_loss(logits, y, grouped, kind) + settings['l2'] * coefficient.square().sum()
        if not torch.isfinite(loss):
            raise ValueError('Nonfinite training loss')
        loss.backward()
        optimizer.step()
        if step in (0, settings['steps'] - 1):
            history.append(float(loss.detach()))
    return dict(**preprocessing, coefficient=coefficient.detach().numpy(), intercept=intercept.detach().numpy(),
                cap=np.array(settings['cap_c']), feature_names=np.asarray(x.columns,dtype=str), history=np.array(history),
                unique_training_inputs=np.array(len(unique)))


def correction(frame, model):
    x = features(frame)
    if list(x) != list(model['feature_names']):
        raise ValueError('Feature order differs from fitted model')
    z = transform(x, model)
    # 저장된 계수의 CPU float32 연산을 고정한다.
    with torch.no_grad():
        delta = float(model['cap']) * torch.tanh(torch.from_numpy(z) @ torch.from_numpy(model['coefficient']) + float(model['intercept']))
    return delta.numpy().astype(float)


def policies(settings):
    result = [dict(candidate='asos_zero' if t == 0 else f'air_{t:g}', model=None, offset=t,
                   complexity=abs(t)) for t in settings['constant_controls_c']]
    for model in settings['models']:
        for offset in settings['offsets_c']:
            result.append(dict(candidate=f'{model}_offset{offset:g}', model=model, offset=offset,
                               complexity=2 + abs(offset)))
    return result


def predictions(frame, specs, cap=2.):
    out = []
    for spec in specs:
        threshold = spec['offset'] if spec['model'] is None else np.clip(frame[spec['model']] + spec['offset'], -cap, cap)
        out.append(np.where(frame.available, frame.asos_air_temp.le(threshold), np.nan))
    return np.column_stack(out)


def choose(table, track):
    base = table.loc[table.candidate.eq('asos_zero')].iloc[0]
    eligible = table
    if track == 'recall_guard':
        eligible = table.loc[table.recall.ge(.9*base.recall) & table.f1_2024.ge(base.f1_2024) & table.f1_2025.ge(base.f1_2025)]
    elif track.startswith('loss_'):
        eligible = table.loc[table.model.eq(track[5:]) | table.candidate.eq('asos_zero')]
    elif track != 'mean_f1':
        raise ValueError('Unknown selection track')
    if eligible.empty:
        return str(base.candidate)
    return str(eligible.sort_values(['f1','complexity','candidate'], ascending=[False,True,True], kind='stable').iloc[0].candidate)
