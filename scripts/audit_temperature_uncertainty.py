"""온도오차 범위의 가중 경험분포·전체 경계·포함률을 별도 계산한다."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.audit_temperature_blind_validation import compare
from scripts.fresh_station_validation import old_freezes, verify_seal

OUT = ROOT / 'outputs/private/temperature_uncertainty_20261010_v1'
SOURCE = ROOT / 'outputs/private/temperature_pair_blending_20261010_v1'


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def radius(frame, name):
    valid = frame.road_temp.notna() & frame[name].notna(); f = frame.loc[valid, ['station', 'road_temp', name]].copy()
    f['error'] = (f[name]-f.road_temp).abs()
    f['weight'] = 1./f.groupby('station').station.transform('size')/f.station.nunique()
    distribution = f.groupby('error', sort=True).weight.sum(); cumulative = distribution.cumsum()/distribution.sum()
    return float(distribution.index[np.flatnonzero(cumulative.to_numpy() >= .9)[0]])


def report(frame, name):
    f = frame.loc[frame.road_temp.notna() & frame[name].notna()].copy()
    y, lo, hi = f.road_temp.to_numpy(), f[name+'_lower'].to_numpy(), f[name+'_upper'].to_numpy()
    inside = (y >= lo) & (y <= hi); widths = hi-lo
    scores = widths+20*np.maximum(lo-y, 0)+20*np.maximum(y-hi, 0)
    st = {}
    for station, positions in f.groupby('station').indices.items():
        st[station] = dict(n=len(positions), coverage=float(np.mean(inside[positions])), width=float(np.mean(widths[positions])), interval_score=float(np.mean(scores[positions])))
    near = np.abs(y) <= 2; cold, warm = hi <= 0, lo > 0
    return dict(n=len(f), nominal_fraction=.9, pooled_coverage=float(np.mean(inside)), station_macro_coverage=float(np.mean([r['coverage'] for r in st.values()])),
                mean_width=float(np.mean(widths)), mean_interval_score=float(np.mean(scores)), stations=st,
                near_freezing=dict(n=int(near.sum()), coverage=float(np.mean(inside[near]))),
                temperature_boundary=dict(cold_decisive_rows=int(cold.sum()), warm_decisive_rows=int(warm.sum()), ambiguous_rows=int((~cold & ~warm).sum()),
                                          false_cold_rows=int(sum(cold & (y > 0))), false_warm_rows=int(sum(warm & (y <= 0)))),
                guaranteed_coverage=False, official_ice_probability=False)


def main():
    target = OUT / 'independent_verification.json'
    if target.exists():
        raise FileExistsError('Preserve completed audit')
    summary = read(OUT / 'summary.json'); groups = read(SOURCE / 'groups.json'); methods = read(OUT / 'experiment_plan.json')['methods']
    for rel, digest in read(OUT / 'input_signatures.json').items():
        assert sha(ROOT / rel) == digest
    for rel, digest in summary['files'].items():
        assert sha(OUT / rel) == digest
    original_summary = read(SOURCE / 'summary.json')
    for rel, digest in original_summary['files'].items():
        assert sha(SOURCE / rel) == digest
    for rel, digest in read(SOURCE / 'input_signatures.json').items():
        assert sha(ROOT / rel) == digest
    intervals = pd.read_parquet(OUT / 'intervals.parquet'); verified = 0
    allowed = set().union(*(set(v) for v in groups.values()))
    assert set(intervals.station) == allowed and intervals.time.ge('2024-11-01').all() and intervals.time.lt('2025-03-01').all()
    for outer in groups:
        calibration = pd.read_parquet(SOURCE / outer / 'inner_oof.parquet'); original = pd.read_parquet(SOURCE / outer / 'outer_predictions.parquet')
        query = intervals.loc[intervals.group.eq(outer)].sort_values(['station', 'time']).reset_index(drop=True)
        original = original.sort_values(['station', 'time']).reset_index(drop=True)
        pd.testing.assert_frame_equal(query[['station', 'time', 'group', 'road_temp', *methods]], original[['station', 'time', 'group', 'road_temp', *methods]])
        assert outer not in set(calibration.group) and not set(calibration.station) & set(query.station)
        for name in methods:
            r = radius(calibration, name); saved = summary['calibrations'][outer][name]
            compare(r, saved['radius']); assert saved['calibration_groups'] == sorted(set(groups)-{outer}) and not saved['outer_labels_used'] and not saved['guaranteed_coverage']
            np.testing.assert_allclose(query[name+'_lower'], query[name]-r, atol=1e-12, rtol=0, equal_nan=True)
            np.testing.assert_allclose(query[name+'_upper'], query[name]+r, atol=1e-12, rtol=0, equal_nan=True); verified += len(query)*2
    for name in methods:
        compare(report(intervals, name), summary['reports'][name])
    freeze = old_freezes()
    for name in ['fresh_station_validation_20261009_v2', 'temperature_blind_20261010_v1', 'temperature_mean_blind_20261010_v1']:
        verify_seal(ROOT / 'outputs/private' / name)
    audit = dict(status='independent_temperature_range_audit_passed', audited_at_utc=datetime.now(timezone.utc).isoformat(), summary_sha256=sha(OUT / 'summary.json'),
                 audit_source_sha256=sha(Path(__file__)), interval_bounds_verified=verified, calibration_quantiles_verified=8, reports_verified=2,
                 old_frozen_files=freeze[0], reserved_frozen_files=freeze[1], guaranteed_coverage=False, new_model_fits=0)
    target.write_text(json.dumps(audit, indent=2), encoding='utf-8'); print(audit)


if __name__ == '__main__':
    main()
