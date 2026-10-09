"""외부 관측 보강 실험의 고정 donor와 그룹별 후보 선택 규칙."""
import numpy as np
import pandas as pd
import hashlib
import json
import shutil
from pathlib import Path

from src.physical_features import CONTEXT_FEATURES
from src.surface_state_context_v2 import SurfaceStateContextV2, STATE_FEATURES
from src.validation import PROTECTED_STATIONS, assert_training_stations
from src.weather_features import haversine_km
from src.data_source import sha256_file


def fit_cache_key(train, forbidden, candidate, signature):
    """값·정답·행 순서·자료형·제외 지점·전체 실험 서명이 같은 학습만 식별한다."""
    payload = {'candidate': candidate, 'forbidden': sorted(map(str, forbidden)),
               'signature': signature, 'columns': list(train.columns),
               'dtypes': [str(t) for t in train.dtypes], 'rows': len(train),
               'values_sha256': hashlib.sha256(pd.util.hash_pandas_object(
                   train, index=True).to_numpy().tobytes()).hexdigest()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


class CompletedFitCache:
    """현재 프로세스 안에서 완료된 학습 산출물만 재사용한다. 원본은 보존한다."""
    def __init__(self):
        self.completed = {}

    def register(self, key, folder):
        folder = Path(folder)
        receipt = folder / 'fit_manifest.json'
        info = json.loads(receipt.read_text(encoding='utf-8'))
        if info.get('fit_cache_key') != key:
            raise ValueError('Completed fit key mismatch')
        self.completed.setdefault(key, (folder, sha256_file(receipt)))

    def materialize(self, key, folder):
        if key not in self.completed:
            return False
        source, receipt_sha = self.completed[key]
        receipt = source / 'fit_manifest.json'
        if sha256_file(receipt) != receipt_sha:
            raise ValueError('Completed fit receipt changed')
        info = json.loads(receipt.read_text(encoding='utf-8'))
        target = Path(folder)
        if info.get('fit_cache_key') != key:
            raise ValueError('Completed fit identity changed')
        for name, digest in info['files'].items():
            if Path(name).name != name or name in {'.', '..', 'fit_manifest.json'}:
                raise ValueError('Unsafe fit artifact name')
            if sha256_file(source / name) != digest:
                raise ValueError('Completed fit artifact changed')
            if (target / name).exists() and sha256_file(target / name) != digest:
                raise ValueError('Preserve conflicting destination artifact')
        if (target / 'fit_manifest.json').exists():
            raise ValueError('Destination fit receipt already exists')
        target.mkdir(parents=True, exist_ok=True)
        for name in info['files']:
            if not (target / name).exists():
                shutil.copy2(source / name, target / name)
            if sha256_file(target / name) != info['files'][name]:
                raise ValueError('Fit copy verification failed')
        shutil.copy2(receipt, target / 'fit_manifest.json')
        evidence = {'fit_cache_key': key, 'source_folder': str(source),
                    'source_fit_manifest_sha256': receipt_sha, 'files': info['files']}
        (target / 'cache_reuse_receipt.json').write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        return True


class FixedDonorStateContext(SurfaceStateContextV2):
    def __init__(self, targets, thermal_source, metadata, state_source, allowed_donors, inventory_before):
        self.allowed_donors = set(map(str, allowed_donors))
        assert_training_stations(self.allowed_donors)
        if not self.allowed_donors <= set(metadata.station):
            raise ValueError('Missing allowed donor metadata')
        if not set(thermal_source.station) <= self.allowed_donors or not set(state_source.station) <= self.allowed_donors:
            raise ValueError('External target observations cannot be dynamic donors')
        super().__init__(targets, thermal_source, metadata, state_source)
        # Future donor observations may be used later for inference, but future sensor
        # availability cannot decide the development reference inventory.
        counts = thermal_source.loc[thermal_source.time.lt(pd.Timestamp(inventory_before))].groupby('station').humidity.count()
        self.metadata['has_moisture'] = self.metadata.index.map(counts).fillna(0) > 0

    def reference(self, target, forbidden, moisture=False):
        excluded = set(forbidden) | {target} | PROTECTED_STATIONS
        point = self.metadata.loc[target]
        pool = self.metadata.loc[self.metadata.index.isin(self.allowed_donors)
                                 & ~self.metadata.index.isin(excluded) & self.metadata.route.eq(point.route)]
        if moisture:
            pool = pool.loc[pool.has_moisture]
        if pool.empty:
            return None, np.nan
        distance, station = min((haversine_km(point.lat, point.lon, row.lat, row.lon), station) for station, row in pool.iterrows())
        return station, distance


def matrix_with_context(frame, context, forbidden, base_features, state=False):
    additions, references = context.features(frame, set(forbidden))
    wanted = CONTEXT_FEATURES + (STATE_FEATURES if state else [])
    if set(base_features) & {'ice', 'state_raw', 'road_temp'}:
        raise ValueError('Target measurements are not predictor columns')
    result = pd.concat([frame[list(base_features)], additions[wanted]], axis=1)
    if result.columns.duplicated().any() or len(result) != len(frame):
        raise ValueError('Feature schema or row mismatch')
    for record in references:
        if record['source'] is not None and record['source'] not in context.allowed_donors - set(forbidden) - {record['target']}:
            raise AssertionError('Forbidden donor selected')
        # Missing references retain NaN predictor values; audit JSON records use null.
        # Non-finite distances for an actual selected source remain an error.
        if not np.isfinite(record['distance_km']):
            if record['source'] is not None:
                raise ValueError('Non-finite distance for selected donor')
            record['distance_km'] = None
    return result, references


def select_group_candidate(rows, held_group, candidate_names):
    """해당 그룹 정답 없이, 다른 그룹 검증의 같은 유효 행에서 FP/FN을 비교한다."""
    relevant = rows.loc[rows.outer_held_group.eq(held_group) & rows.validation_group.ne(held_group)].copy()
    if relevant.empty:
        raise ValueError('No nested group comparison available')
    expected_groups = set(relevant.validation_group)
    if len(expected_groups) != 3:
        raise ValueError('Expected the other three development groups')
    totals = {}
    for name in ['baseline', *candidate_names]:
        part = relevant.loc[relevant.candidate.eq(name)]
        if len(part) != 3 or set(part.validation_group) != expected_groups or part.validation_group.duplicated().any():
            raise ValueError('Incomplete nested candidate comparison')
        for record in part.itertuples():
            if not {held_group, record.validation_group} <= set(record.training_excluded_groups):
                raise ValueError('Held groups influenced fitting or calibration')
        totals[name] = {key: int(part[key].sum()) for key in ['n', 'tp', 'fp', 'fn', 'tn']}
    baseline = totals['baseline']
    accepted = []
    for name in candidate_names:
        candidate = totals[name]
        if candidate['n'] != baseline['n'] or candidate['tp'] + candidate['fn'] != baseline['tp'] + baseline['fn']:
            raise ValueError('Candidate comparison uses different gold rows')
        if candidate['fp'] < baseline['fp'] and candidate['fn'] < baseline['fn']:
            denominator = 2 * candidate['tp'] + candidate['fp'] + candidate['fn']
            f1 = 2 * candidate['tp'] / denominator if denominator else 0.
            accepted.append((f1, -candidate['fp'], -candidate['fn'], name))
    selected = max(accepted)[-1] if accepted else 'baseline'
    return {'held_group': held_group, 'selected_candidate': selected, 'selection_groups': sorted(expected_groups),
            'selection_excludes_held_group': True, 'require_both_fp_fn_improvement': True,
            'selection_totals': totals, 'scope': 'Other-group first-winter development comparisons only; reserved winter unopened.'}
