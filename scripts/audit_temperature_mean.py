"""평균 후보의 성분·내부 선택·고정 수분 판정·지표를 생산 코드와 별개로 검산한다."""
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
from scripts.audit_temperature_blind_validation import reference_temperature, reference_ice, compare
from scripts.fresh_station_validation import old_freezes, verify_seal

DEFAULT = ROOT / 'outputs/private/temperature_mean_20261010_v1'
SOURCE = ROOT / 'outputs/private/weather_distance_20261010_v1'
CANDIDATE = 'equal_mean_weather14_weather12'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def temperatures(frame, name):
    report = reference_temperature(frame, name)
    near = reference_temperature(frame.loc[frame.road_temp.between(-2, 2)], name)
    return {key: report[key] for key in ['pooled', 'stations', 'station_macro']} | {'near_freezing': near['pooled']}


def independent_gate(reports, maximum_harm):
    base, candidate = reports['direct_weather14'], reports[CANDIDATE]
    assert set(base['stations']) == set(candidate['stations'])
    assert all(base['stations'][s]['n'] == candidate['stations'][s]['n'] for s in base['stations'])
    assert base['near_freezing']['n'] == candidate['near_freezing']['n']
    ok = all(candidate['station_macro'][name] < base['station_macro'][name] - 1e-12 for name in ['mae', 'rmse'])
    ok &= all(candidate['stations'][s]['mae'] <= values['mae']*(1+maximum_harm)+1e-12 for s, values in base['stations'].items())
    ok &= candidate['near_freezing']['mae'] <= base['near_freezing']['mae']+1e-12
    return CANDIDATE if ok else 'direct_weather14'


def verify_mean(frame):
    a, b = frame.direct_weather14.to_numpy(), frame.weather12_no_distance.to_numpy()
    assert np.array_equal(np.isfinite(a), np.isfinite(b))
    # 生産 모듈의 평균 함수를 호출하지 않는다.
    p = np.array([(x+y)/2 if np.isfinite(x) else np.nan for x, y in zip(a, b)])
    np.testing.assert_allclose(frame[CANDIDATE], p, atol=1e-12, rtol=0, equal_nan=True)
    return len(p)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, default=DEFAULT)
    out = parser.parse_args().experiment.resolve(); target = out / 'independent_verification.json'
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()) or target.exists():
        raise ValueError('New private audit receipt required')
    summary, plan = read(out / 'summary.json'), read(out / 'experiment_plan.json')
    for rel, digest in read(out / 'input_signatures.json').items():
        assert sha(ROOT / rel) == digest, rel
    for rel, digest in summary['files'].items():
        assert sha(out / rel) == digest, rel
    source = read(out / 'component_source_receipt.json')
    assert sha(SOURCE / 'summary.json') == source['source_summary_sha256']
    for rel, digest in source['source_files'].items():
        assert sha(SOURCE / rel) == digest, rel
    assert plan['weights'] == [.5, .5] and not summary['weight_search_performed'] and summary['new_model_fits'] == 0
    groups = {g: set(v) for g, v in read(out / 'groups.json').items()}
    external = set().union(*groups.values()); decisions = read(out / 'decisions.json')
    verified = 0; parts = []
    for group, held in groups.items():
        inner = pd.read_parquet(out / group / 'inner_oof.parquet')
        original = pd.read_parquet(SOURCE / group / 'inner_oof.parquet')
        pd.testing.assert_frame_equal(inner[original.columns], original)
        assert set(inner.station) == external-held and not inner.duplicated(['station', 'time']).any()
        verified += verify_mean(inner)
        reports = {name: temperatures(inner, name) for name in ['direct_weather14', CANDIDATE]}
        compare(reports, decisions[group]['inner_reports'])
        chosen = independent_gate(reports, plan['maximum_station_harm'])
        assert chosen == decisions[group]['selected_candidate']
        assert set(decisions[group]['excluded_stations']) == held and not decisions[group]['outer_labels_used_for_selection']
        assert set(decisions[group]['selection_groups']) == set(groups)-{group}
        outer = pd.read_parquet(out / group / 'outer_predictions.parquet')
        original = pd.read_parquet(SOURCE / group / 'outer_predictions.parquet')
        pd.testing.assert_frame_equal(outer[original.columns[:6]], original.iloc[:, :6])
        assert set(outer.station) == held
        verified += verify_mean(outer)
        np.testing.assert_allclose(outer.selected_temperature, outer[chosen], rtol=0, atol=0, equal_nan=True)
        parts.append(outer)
    combined = pd.read_parquet(out / 'outer_predictions.parquet')
    expected = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(combined, expected)
    compare({name: temperatures(combined, name) for name in summary['metrics']}, summary['metrics'])
    classified = pd.read_parquet(out / 'ice_diagnostic_predictions.parquet')
    keys = ['station', 'time']
    pd.testing.assert_frame_equal(classified[combined.columns], combined)
    label_path = ROOT / 'outputs/private/daily_primary_transfer_20261009_v1/predictions.parquet'
    labels = pd.read_parquet(label_path).set_index(keys).loc[pd.MultiIndex.from_frame(classified[keys])]
    np.testing.assert_allclose(classified.ice, labels.ice, rtol=0, atol=0, equal_nan=True)
    np.testing.assert_array_equal(classified.baseline_prediction, labels.baseline_prediction)
    data = pd.read_parquet(SOURCE / 'development_inputs.parquet').set_index(keys).loc[pd.MultiIndex.from_frame(classified[keys])]
    water = data[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
    for name, report in summary['ice_diagnostic'].items():
        t = classified[name].to_numpy(); fallback = ~np.isfinite(t) | np.isnan(water).all(axis=1)
        p = ((t <= 0) & ((water[:, 0] >= t) | (water[:, 1] > 0) | (water[:, 2] > 0))).astype(int)
        p[fallback] = classified.baseline_prediction.to_numpy()[fallback]
        np.testing.assert_array_equal(p, classified['ice_'+name])
        compare(reference_ice(classified, 'ice_'+name) | {'fallback_rows': int(fallback.sum())}, report)
    valid = np.isfinite(combined.road_temp) & np.isfinite(combined[CANDIDATE])
    a = combined.loc[valid, 'direct_weather14'].to_numpy()-combined.loc[valid, 'road_temp'].to_numpy()
    b = combined.loc[valid, 'weather12_no_distance'].to_numpy()-combined.loc[valid, 'road_temp'].to_numpy()
    observed = summary['component_error_diagnostics']
    np.testing.assert_allclose([observed['error_correlation'], observed['mixture_mse'], observed['mse_identity']],
                              [np.corrcoef(a, b)[0, 1], np.mean(((a+b)/2)**2), np.mean(a*a)/4+np.mean(b*b)/4+np.mean(a*b)/2], rtol=0, atol=1e-12)
    overall = independent_gate(summary['metrics'], plan['maximum_station_harm']) == CANDIDATE
    assert overall == summary['development_overall_temperature_gate_passed']
    freezes = old_freezes()
    for name in ['temperature_blind_20261010_v1', 'fresh_station_validation_20261009_v2']:
        verify_seal(ROOT / 'outputs/private' / name)
    result = dict(status='independent_equal_mean_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(),
                  summary_sha256=sha(out / 'summary.json'), audit_source_sha256=sha(Path(__file__)),
                  combined_prediction_values_verified=verified, decisions_verified=4, temperature_variants_verified=4, ice_policies_verified=4,
                  development_overall_temperature_gate_passed=overall, weight_search_performed=False, new_model_fits=0,
                  old_frozen_files=freezes[0], reserved_frozen_files=freezes[1], candidate_promoted=False)
    with target.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False); handle.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
