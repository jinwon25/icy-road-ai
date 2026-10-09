"""첫 겨울 OOF 임계값만으로 사전 고정한 두 모델 결합을 비교한다."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.frozen_assessment import verify_freeze
from src.validation import assert_training_stations, binary_metrics, daily_scores, macro_scores
from src.ice_daily_selection import choose_daily_threshold
from scripts.baseline_ice_logistic import choose_threshold
from scripts.evaluate_physical_ice import threshold_grid


def combine(a, b, name):
    if not np.isfinite(a).all() or not np.isfinite(b).all() or not ((a >= 0) & (a <= 1) & (b >= 0) & (b <= 1)).all():
        raise ValueError('Invalid input scores')
    if name == 'arithmetic':
        return (a + b) / 2
    if name == 'geometric':
        return np.sqrt(a * b)
    raise ValueError(name)


def main():
    private = ROOT / 'outputs/private'
    config_path = ROOT / 'config/surface_state_ensemble.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    aroot, broot = private / 'forward_physics', private / 'surface_state_forward'
    frozen = verify_freeze(ROOT)
    for root in [aroot, broot]:
        audit_path = root / 'audit.json'
        if root == broot:
            audit = json.loads(audit_path.read_text(encoding='utf-8'))
            if audit['protected_data_used'] or audit['predictions_sha256'] != sha256_file(root / 'predictions.parquet'):
                raise AssertionError('Unverified state predictions')
    columns = ['station', 'time', 'ice']
    keys = ['station', 'time']
    a = pd.read_parquet(aroot / 'predictions.parquet').sort_values(keys).reset_index(drop=True)
    b = pd.read_parquet(broot / 'predictions.parquet').sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(a[columns], b[columns])
    assert_training_stations(a.station.unique())
    if len(a.station.unique()) != 14 or a.duplicated(keys).any() or a.time.min() < pd.Timestamp(config['validate_from']):
        raise AssertionError('Outer grid mismatch')
    out = private / 'surface_state_ensemble'; out.mkdir(exist_ok=True)
    signature = {'config': sha256_file(config_path), 'runner': sha256_file(Path(__file__)),
                 'thermal_predictions': sha256_file(aroot / 'predictions.parquet'),
                 'state_predictions': sha256_file(broot / 'predictions.parquet')}
    for held in sorted(a.station.unique()):
        for name, root in [('thermal', aroot), ('state', broot)]:
            signature[f'{held}_{name}_oof'] = sha256_file(root / held / 'inner_oof.parquet')
            signature[f'{held}_{name}_references'] = sha256_file(root / held / 'references.json')
    signature_path = out / 'input_signature.json'
    if signature_path.exists() and json.loads(signature_path.read_text(encoding='utf-8')) != signature:
        raise ValueError('Changed inputs; preserve prior experiment')
    signature_path.write_text(json.dumps(signature, indent=2), encoding='utf-8')
    result = a[columns + ['score_thermal', 'pred_slot_thermal', 'pred_daily_thermal']].copy()
    choices = []; inner_rows = reference_count = 0
    for name in config['candidates']:
        result[f'score_{name}'] = combine(a.score_thermal.to_numpy(), b.score_surface_state.to_numpy(), name)
        for policy in ['slot', 'daily']:
            result[f'pred_{policy}_{name}'] = 0
    for held in sorted(a.station.unique()):
        folder = out / held; folder.mkdir(exist_ok=True)
        ai = pd.read_parquet(aroot / held / 'inner_oof.parquet').sort_values(keys).reset_index(drop=True)
        bi = pd.read_parquet(broot / held / 'inner_oof.parquet').sort_values(keys).reset_index(drop=True)
        pd.testing.assert_frame_equal(ai[columns], bi[columns])
        assert_training_stations(ai.station.unique())
        if ai.station.eq(held).any() or ai.time.max() >= pd.Timestamp(config['train_before']) or ai.ice.isna().any() or ai.duplicated(keys).any():
            raise AssertionError('Inner OOF partition mismatch')
        for root in [aroot, broot]:
            refs = json.loads((root / held / 'references.json').read_text(encoding='utf-8'))
            for ref in refs:
                assert_training_stations([ref['source']])
                if held not in ref['forbidden'] or ref['source'] in set(ref['forbidden']) | {ref['target']}:
                    raise AssertionError('Forbidden reference')
                reference_count += 1
        inner_rows += len(ai)
        mask = result.station.eq(held)
        for name in config['candidates']:
            score = combine(ai.score_thermal.to_numpy(), bi.score_surface_state.to_numpy(), name)
            slot_t, slot_f1 = choose_threshold(ai.ice.to_numpy(dtype=int), score)
            daily_t, daily_f1, trace = choose_daily_threshold(ai, score, threshold_grid(score))
            trace.to_csv(folder / f'{name}_trace.csv', index=False)
            choices.append({'station': held, 'candidate': name, 'slot_threshold': slot_t, 'daily_threshold': daily_t,
                            'inner_slot_f1': slot_f1, 'inner_daily_f1': daily_f1})
            for policy, threshold in [('slot', slot_t), ('daily', daily_t)]:
                result.loc[mask, f'pred_{policy}_{name}'] = (result.loc[mask, f'score_{name}'] >= threshold).astype(int)
        print(held, 'OOF aligned and thresholds selected', flush=True)
    metrics = {}; all_days = []
    good = result.loc[result.ice.notna()]
    for name in ['thermal', *config['candidates']]:
        for policy in ['slot', 'daily']:
            col = f'pred_{policy}_{name}'
            records = [(r.station, r.time, int(r.ice) if pd.notna(r.ice) else None, int(getattr(r, col))) for r in result.itertuples()]
            daily = daily_scores(records, minimum_coverage=1.); days = pd.DataFrame(daily)
            accepted = days.loc[days.accepted]; fixed = accepted.loc[(accepted.tp + accepted.fn).gt(0)]
            metrics[f'{name}_{policy}'] = {'slot_micro': binary_metrics(good.ice.astype(int), good[col]),
                'average_precision': float(average_precision_score(good.ice, good[f'score_{name}'])),
                'roc_auc': float(roc_auc_score(good.ice, good[f'score_{name}'])), 'daily_station_macro': macro_scores(daily),
                'fixed_ice_day_f1': float(fixed.groupby('station').f1.mean().mean()),
                'false_alarm_nonice_days': int(accepted.loc[(accepted.tp + accepted.fn).eq(0), 'fp'].gt(0).sum())}
            days['variant'] = f'{name}_{policy}'; all_days.append(days)
    result.to_parquet(out / 'predictions.parquet', index=False, compression='zstd')
    pd.DataFrame(choices).to_csv(out / 'thresholds.csv', index=False)
    pd.concat(all_days).to_csv(out / 'daily_metrics.csv', index=False, encoding='utf-8-sig')
    summary = {'status': 'fixed_equal_weight_ensemble_development_only', 'rows': len(result), 'metrics': metrics,
               'config': config, 'signature': signature, 'matched_first_winter_oof_rows': inner_rows,
               'reference_records_checked': reference_count, 'protected_data_used': False,
               'frozen_files_unchanged': len(frozen['files']), 'independent_final_test': False}
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(metrics), flush=True)


if __name__ == '__main__':
    main()
