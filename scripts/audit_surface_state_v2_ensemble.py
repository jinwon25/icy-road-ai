"""결합 후보의 전체 점수·내부 선택·혼동행렬을 입력에서 재계산한다."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.frozen_assessment import verify_freeze
from src.validation import assert_training_stations
from src.ice_daily_selection import choose_daily_threshold
from scripts.baseline_ice_logistic import choose_threshold
from scripts.evaluate_physical_ice import threshold_grid


def main():
    private = ROOT / 'outputs/private'; out = private / 'surface_state_v2_ensemble'
    summary = json.loads((out / 'summary.json').read_text(encoding='utf-8'))
    config = json.loads((ROOT / 'config/surface_state_v2_ensemble.json').read_text(encoding='utf-8'))
    assert config == summary['config']
    assert config['weights'] == [0.5, 0.5] and config['candidates'] == ['arithmetic', 'geometric']
    assert sha256_file(ROOT / 'config/surface_state_v2_ensemble.json') == summary['signature']['config']
    assert sha256_file(ROOT / 'scripts/evaluate_surface_state_v2_ensemble.py') == summary['signature']['runner']
    keys, targets = ['station', 'time'], ['station', 'time', 'ice']
    aroot, broot = private / 'forward_physics', private / 'surface_state_v2_forward'
    a = pd.read_parquet(aroot / 'predictions.parquet').sort_values(keys).reset_index(drop=True)
    b = pd.read_parquet(broot / 'predictions.parquet').sort_values(keys).reset_index(drop=True)
    result = pd.read_parquet(out / 'predictions.parquet').sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(a[targets], b[targets]); pd.testing.assert_frame_equal(a[targets], result[targets])
    assert_training_stations(result.station.unique())
    choices = pd.read_csv(out / 'thresholds.csv', dtype={'station': str}, float_precision='round_trip')
    assert len(choices) == 28 and not choices.duplicated(['station', 'candidate']).any()
    rows = 0; references = 0
    for held in sorted(a.station.unique()):
        ai = pd.read_parquet(aroot / held / 'inner_oof.parquet').sort_values(keys).reset_index(drop=True)
        bi = pd.read_parquet(broot / held / 'inner_oof.parquet').sort_values(keys).reset_index(drop=True)
        pd.testing.assert_frame_equal(ai[targets], bi[targets]); assert_training_stations(ai.station.unique())
        assert not ai.station.eq(held).any() and ai.time.max() < pd.Timestamp(config['train_before'])
        for label, root in [('thermal', aroot), ('state', broot)]:
            assert sha256_file(root / held / 'inner_oof.parquet') == summary['signature'][f'{held}_{label}_oof']
            path = root / held / 'references.json'
            assert sha256_file(path) == summary['signature'][f'{held}_{label}_references']
            for ref in json.loads(path.read_text(encoding='utf-8')):
                assert_training_stations([ref['source']])
                assert held in ref['forbidden'] and ref['source'] not in set(ref['forbidden']) | {ref['target']}
                references += 1
        for name in config['candidates']:
            x, y = ai.score_thermal.to_numpy(), bi.score_surface_state_v2.to_numpy()
            inner = (x + y) * 0.5 if name == 'arithmetic' else np.sqrt(x * y)
            choice = choices.loc[choices.station.eq(held) & choices.candidate.eq(name)].iloc[0]
            slot_t, slot_f1 = choose_threshold(ai.ice.to_numpy(dtype=int), inner)
            daily_t, daily_f1, trace = choose_daily_threshold(ai, inner, threshold_grid(inner))
            np.testing.assert_allclose([slot_t, slot_f1, daily_t, daily_f1],
                [choice.slot_threshold, choice.inner_slot_f1, choice.daily_threshold, choice.inner_daily_f1], rtol=0, atol=1e-12)
            # 저장 점수와 실제 이진 판정도 전체 행에서 별도로 대조한다.
            x, y = a.score_thermal.to_numpy(), b.score_surface_state_v2.to_numpy()
            score = (x + y) * 0.5 if name == 'arithmetic' else np.sqrt(x * y)
            np.testing.assert_allclose(result[f'score_{name}'], score, rtol=0, atol=1e-15)
            mask = result.station.eq(held)
            for policy, threshold in [('slot', choice.slot_threshold), ('daily', choice.daily_threshold)]:
                np.testing.assert_array_equal(result.loc[mask, f'pred_{policy}_{name}'], score[mask] >= threshold)
        rows += len(ai)
    valid = result.loc[result.ice.notna()]
    for key, metric in summary['metrics'].items():
        name, policy = key.rsplit('_', 1)
        tn, fp, fn, tp = confusion_matrix(valid.ice, valid[f'pred_{policy}_{name}'], labels=[0, 1]).ravel()
        assert (tn, fp, fn, tp) == tuple(metric['slot_micro'][k] for k in ['tn', 'fp', 'fn', 'tp'])
        np.testing.assert_allclose([average_precision_score(valid.ice, valid[f'score_{name}']), roc_auc_score(valid.ice, valid[f'score_{name}'])],
                                  [metric['average_precision'], metric['roc_auc']], rtol=0, atol=1e-15)
    assert rows == summary['matched_first_winter_oof_rows'] and references == summary['reference_records_checked']
    for label, root in [('thermal', aroot), ('state', broot)]:
        assert sha256_file(root / 'predictions.parquet') == summary['signature'][f'{label}_predictions']
    frozen = verify_freeze(ROOT)
    audit = {'status': 'surface_state_v2_ensemble_audit_passed', 'score_rows_recomputed': len(result) * 2,
             'matched_first_winter_oof_rows': rows, 'threshold_choices_reselected': len(choices),
             'reference_records_checked': references, 'confusion_ap_roc_recomputed': True,
             'protected_data_used': False, 'frozen_files_unchanged': len(frozen['files']),
             'summary_sha256': sha256_file(out / 'summary.json'), 'predictions_sha256': sha256_file(out / 'predictions.parquet')}
    (out / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit), flush=True)


if __name__ == '__main__':
    main()
