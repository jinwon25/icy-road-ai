"""이력 대조군에도 기존 온도·결빙·사건 유지 기준을 그대로 적용한다."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.method_blending import ice_guard
from scripts.audit_weather_memory_temperature import ice_checks
from scripts.evaluate_method_blending import read, write, preservation

PRIVATE = ROOT / 'outputs/private'
SOURCE = PRIVATE / 'weather_memory_temperature_20261013_v2'
CONTROLS = PRIVATE / 'weather_memory_controls_20261013_v1'
OUT = PRIVATE / 'weather_memory_tradeoffs_20261013_v1'
BASELINE = 'equal_distance_mse_mae300'


def main():
    if OUT.exists(): raise FileExistsError('Preserve tradeoff review')
    audit = read(CONTROLS / 'independent_verification.json'); summary = read(CONTROLS / 'summary.json'); original = read(SOURCE / 'summary.json')
    assert audit['status'] == 'independent_same_parameter_memory_controls_audit_passed' and audit['summary_sha256'] == sha(CONTROLS / 'summary.json')
    baseline_stations = pd.read_csv(SOURCE / f'ice_stations_{BASELINE}.csv', dtype={'station': str})
    records, pinned = {}, [Path(__file__), ROOT / 'src/method_blending.py', ROOT / 'scripts/audit_weather_memory_temperature.py',
          CONTROLS / 'summary.json', CONTROLS / 'independent_verification.json', SOURCE / 'summary.json', SOURCE / f'ice_stations_{BASELINE}.csv']
    for name, r in summary['ice_diagnostic'].items():
        path = CONTROLS / f'ice_stations_{name}.csv'; pinned.append(path); stations = pd.read_csv(path, dtype={'station': str})
        eligible, checks = ice_guard(r, original['ice_diagnostic'][BASELINE], stations, baseline_stations)
        independent = ice_checks(r, original['ice_diagnostic'][BASELINE], stations, baseline_stations)
        assert eligible == independent['eligible'] and checks == independent['checks']
        events = audit['event_identity_checks'][name]
        records[name] = dict(temperature_eligible=summary['gate_vs_original_trio'][name], previous_ice_guard_eligible=eligible,
             ice_guard_checks=checks, event_retention_eligible=events['eligible_no_event_loss'], lost_events=events['lost_events'], gained_events=events['gained_events'],
             combined_eligible=bool(summary['gate_vs_original_trio'][name] and eligible and events['eligible_no_event_loss']))
    OUT.mkdir(); freezes = preservation()
    write(OUT / 'review.json', dict(status='same_parameter_control_tradeoffs_verified', checked_at_utc=datetime.now(timezone.utc).isoformat(), comparisons=records,
         input_signatures={str(p.relative_to(ROOT)): sha(p) for p in pinned}, original_choices_changed=False, model_promoted=False,
         old_frozen_files=freezes[0], reserved_frozen_files=freezes[1]))
    for name, r in records.items(): print(name, r)


if __name__ == '__main__': main()
