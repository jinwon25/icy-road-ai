"""후속 고정 쌍·삼중 평균의 산술·300단독 대조·물리 판정을 별도 검산한다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.audit_method_blending import report, gate
from scripts.audit_temperature_blind_validation import reference_ice, compare
from scripts.fresh_station_validation import old_freezes, verify_seal


def read(p):
    return json.loads(Path(p).read_text('utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, default=ROOT / 'outputs/private/temperature_pair_blending_20261010_v1')
    out = parser.parse_args().experiment.resolve(); target = out / 'independent_verification.json'
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()) or target.exists():
        raise ValueError('New private audit receipt required')
    summary, plan = read(out / 'summary.json'), read(out / 'experiment_plan.json')
    for rel, digest in read(out / 'input_signatures.json').items():
        assert sha(ROOT / rel) == digest, rel
    for rel, digest in summary['files'].items():
        assert sha(out / rel) == digest, rel
    blends, baseline = plan['blends'], plan['primary_baseline']; decisions = read(out / 'decisions.json'); parts = []; checked = 0
    for outer in read(out / 'groups.json'):
        inner = pd.read_parquet(out / outer / 'inner_oof.parquet'); result = pd.read_parquet(out / outer / 'outer_predictions.parquet')
        for kind, frame in [('inner_oof', inner), ('outer_predictions', result)]:
            original = pd.read_parquet(ROOT / 'outputs/private/method_blending_20261010_v2' / outer / (kind+'.parquet'))
            columns = [c for c in original if c not in ['selected_candidate', 'selected_temperature']]
            pd.testing.assert_frame_equal(frame[columns], original[columns])
            for name, components in blends.items():
                first = np.isfinite(frame[components[0]])
                assert all(np.array_equal(first, np.isfinite(frame[c])) for c in components)
                expected = sum(frame[c].to_numpy()/len(components) for c in components)
                np.testing.assert_allclose(frame[name], expected, atol=1e-12, rtol=0, equal_nan=True); checked += len(frame)
        reports = {c: report(inner, c) for c in [baseline, *blends]}; compare(reports, decisions[outer]['inner_reports'])
        eligible = [c for c in blends if gate(reports[c], reports[baseline])]
        chosen = min(eligible, key=lambda c: (reports[c]['station_macro']['mae'], reports[c]['station_macro']['rmse'], c)) if eligible else baseline
        assert chosen == decisions[outer]['selected_candidate'] and not decisions[outer]['outer_labels_used_for_selection']
        np.testing.assert_allclose(result.selected_temperature, result[chosen], atol=0, rtol=0, equal_nan=True); parts.append(result)
    combined = pd.read_parquet(out / 'outer_predictions.parquet')
    pd.testing.assert_frame_equal(combined, pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True))
    reports = {c: report(combined, c) for c in summary['metrics']}; compare(reports, summary['metrics'])
    for c, ok in summary['development_gate_vs_mse300'].items():
        assert gate(reports[c], reports[baseline]) == ok
    classified = pd.read_parquet(out / 'ice_predictions.parquet'); pd.testing.assert_frame_equal(classified[combined.columns], combined)
    labels = pd.read_parquet(ROOT / 'outputs/private/method_blending_20261010_v2/ice_predictions.parquet').set_index(['station', 'time'])
    expected = labels.loc[pd.MultiIndex.from_frame(classified[['station', 'time']])]
    np.testing.assert_allclose(classified.ice, expected.ice, rtol=0, atol=0, equal_nan=True)
    np.testing.assert_array_equal(classified.baseline_prediction, expected.baseline_prediction)
    data = pd.read_parquet(ROOT / 'outputs/private/weather_distance_20261010_v1/development_inputs.parquet').set_index(['station', 'time'])
    water = data.loc[pd.MultiIndex.from_frame(combined[['station', 'time']]), ['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
    for c, r in summary['ice_diagnostic'].items():
        t = classified[c].to_numpy(); fallback = ~np.isfinite(t) | np.isnan(water).all(axis=1)
        p = ((t <= 0) & ((water[:, 0] >= t) | (water[:, 1] > 0) | (water[:, 2] > 0))).astype(int)
        p[fallback] = classified.baseline_prediction.to_numpy()[fallback]
        np.testing.assert_array_equal(p, classified['ice_'+c]); compare(reference_ice(classified, 'ice_'+c) | {'fallback_rows': int(fallback.sum())}, r)
    freezes = old_freezes()
    for name in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1', 'temperature_mean_blind_20261010_v1']:
        verify_seal(ROOT / 'outputs/private' / name)
    audit = dict(status='independent_fixed_pairs_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
                 summary_sha256=sha(out / 'summary.json'), audit_source_sha256=sha(Path(__file__)),
                 blend_prediction_values_verified=checked, decisions_verified=4, temperature_variants_verified=6, thermal_policies_verified=5,
                 new_base_fits=0, learned_weights=0, old_frozen_files=freezes[0], reserved_frozen_files=freezes[1], model_promoted=False)
    with target.open('x', encoding='utf-8') as f:
        json.dump(audit, f, indent=2)
    print(json.dumps(audit))


if __name__ == '__main__':
    main()
