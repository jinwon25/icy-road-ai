"""다음 겨울 정답 수집 전에 고정 예측·모델·소스의 완전성을 확인한다."""
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data_source import sha256_file
from src.kma_rwis_download import validate_development_request
from src.kma_rwis_transport import ValidatedRoadClient

PREDICTION_COLUMNS = ['station', 'time', 'group', 'selected_candidate', 'temperature_candidate',
                      'baseline_ice_score', 'selected_ice_score', 'baseline_prediction', 'selected_prediction',
                      'baseline_threshold', 'selected_threshold', 'baseline_temperature_c', 'selected_temperature_c']


def reserved_times(plan):
    return pd.date_range(plan['reserved_validation_start_kst'],
                         pd.Timestamp(plan['reserved_validation_end_kst']) + pd.Timedelta(hours=23, minutes=50), freq='10min')


def validate_reserved_predictions(frame, plan):
    if set(frame) != set(PREDICTION_COLUMNS):
        raise ValueError('Only complete prediction columns, no target outcomes, are accepted')
    stations = {str(s): group for group, ids in plan['station_groups'].items() for s in ids}
    if set(frame.station) != set(stations) or frame.duplicated(['station', 'time']).any():
        raise ValueError('Incomplete or duplicate reserved prediction stations')
    times = reserved_times(plan)
    for station, part in frame.groupby('station'):
        if not pd.DatetimeIndex(part.time.sort_values()).equals(times):
            raise ValueError('Every planned reserved ten-minute slot must be predicted before outcomes')
        if not part.group.eq(stations[station]).all():
            raise ValueError('Unexpected spatial group')
        for threshold in ('baseline_threshold', 'selected_threshold'):
            if part[threshold].nunique(dropna=False) != 1:
                raise ValueError('Threshold changes during reserved winter')
    for prefix in ('baseline', 'selected'):
        scores = frame[f'{prefix}_ice_score'].to_numpy()
        threshold = frame[f'{prefix}_threshold'].to_numpy()
        if not np.isfinite(scores).all() or not np.isfinite(threshold).all() or not ((0 <= scores) & (scores <= 1)).all():
            raise ValueError('Invalid reserved classifier score or threshold')
        if not np.array_equal(frame[f'{prefix}_prediction'].to_numpy(), (scores >= threshold).astype(int)):
            raise ValueError('Predicted labels differ from frozen threshold')
        temperature = frame[f'{prefix}_temperature_c'].to_numpy()
        if np.isinf(temperature).any():
            raise ValueError('Infinite reserved temperature prediction')
    if not np.array_equal(np.isfinite(frame.baseline_temperature_c), np.isfinite(frame.selected_temperature_c)):
        raise ValueError('Temperature candidates use different prediction domains')


def _safe_file(root, relative):
    root = Path(root).resolve(); path = (root / relative).resolve()
    if not path.is_relative_to(root) or path.name == 'secret.env' or path.suffix == '.env':
        raise ValueError('Invalid frozen evidence path')
    return path


def seal_reserved_predictions(root, out, plan_path, frozen_files):
    root, out, plan_path = Path(root), Path(out), Path(plan_path)
    receipt_path = out / 'predictions_receipt.json'
    if receipt_path.exists():
        raise FileExistsError('Reserved predictions already sealed; do not replace')
    if (root / 'outputs/private/external/kma_rwis_reserved_v1').exists():
        raise ValueError('Reserved outcome collection already exists; new prediction sealing prohibited')
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    frame = pd.read_parquet(out / 'predictions.parquet')
    validate_reserved_predictions(frame, plan)
    files = {str(plan_path.relative_to(root)).replace('\\', '/'): sha256_file(plan_path)}
    for relative in frozen_files:
        files[relative] = sha256_file(_safe_file(root, relative))
    for path in out.rglob('*'):
        if path.is_file() and path.suffix != '.tmp':
            files[path.relative_to(root).as_posix()] = sha256_file(path)
    receipt = {'status': 'reserved_predictions_fixed_before_outcomes', 'sealed_at_utc': datetime.now(timezone.utc).isoformat(),
               'rows': len(frame), 'stations': sorted(frame.station.unique()), 'plan': plan,
               'reserved_outcomes_opened_at_seal': False, 'protected_outcomes_used': False,
               'files': files, 'prediction_relative_path': (out / 'predictions.parquet').relative_to(root).as_posix()}
    with receipt_path.open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return receipt


def verify_reserved_freeze(root, out):
    root, out = Path(root), Path(out)
    receipt = json.loads((out / 'predictions_receipt.json').read_text(encoding='utf-8'))
    if receipt['status'] != 'reserved_predictions_fixed_before_outcomes' or receipt['reserved_outcomes_opened_at_seal']:
        raise ValueError('Invalid reserved prediction receipt')
    for relative, checksum in receipt['files'].items():
        if sha256_file(_safe_file(root, relative)) != checksum:
            raise ValueError(f'Reserved frozen evidence changed: {relative}')
    frame = pd.read_parquet(_safe_file(root, receipt['prediction_relative_path']))
    validate_reserved_predictions(frame, receipt['plan'])
    if len(frame) != receipt['rows']:
        raise ValueError('Reserved row count changed')
    return receipt


def reserved_request_plan(receipt):
    if receipt['status'] != 'reserved_predictions_fixed_before_outcomes' or receipt['reserved_outcomes_opened_at_seal']:
        raise ValueError('Prediction freeze required before reserved requests')
    # This private transport view changes only date bounds. The original plan and
    # development collector remain pinned and unable to request the reserved winter.
    plan = dict(receipt['plan'])
    plan['development_start_kst'] = plan['reserved_validation_start_kst']
    plan['development_end_kst'] = plan['reserved_validation_end_kst']
    return plan


class ReservedRoadClient:
    def __init__(self, root, freeze_folder, key, cache, session=None):
        receipt = verify_reserved_freeze(root, freeze_folder)
        self.plan = reserved_request_plan(receipt)
        self.client = ValidatedRoadClient(self.plan, key, cache, session=session)

    def fetch(self, station, start, end):
        validate_development_request(self.plan, station, start, end)
        return self.client.fetch(station, start, end)
