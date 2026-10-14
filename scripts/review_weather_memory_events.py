"""행별 예측에서 사건을 별도로 재구성해 순증가와 기존 사건 손실을 구별한다."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.event_retention import compare_event_retention
from scripts.evaluate_method_blending import read, write, preservation

STUDY = ROOT / 'outputs/private/weather_memory_temperature_20261013_v2'
OUT = ROOT / 'outputs/private/weather_memory_event_review_20261013_v1'
BASELINE = 'equal_distance_mse_mae300'


def reconstruct(frame, column):
    records = []
    for station, f in frame.groupby('station'):
        f = f.sort_values('time'); previous, was_ice, event = None, False, None
        for t, y, p in zip(f.time, f.ice, f[column]):
            positive = y == 1
            continuation = positive and was_ice and t-previous == pd.Timedelta(minutes=10)
            if positive:
                if not continuation:
                    if event is not None: records.append(event)
                    event = dict(station=station, start_kst=str(t), slots=0, detected_slots=0)
                event['slots'] += 1; event['detected_slots'] += int(p)
            elif event is not None:
                records.append(event); event = None
            previous, was_ice = t, positive
        if event is not None: records.append(event)
    return pd.DataFrame(records)


def main():
    if OUT.exists(): raise FileExistsError('Preserve event review')
    audit = read(STUDY / 'independent_verification.json')
    assert audit['summary_sha256'] == sha(STUDY / 'summary.json') and audit['status'] == 'independent_weather_memory_temperature_audit_passed'
    summary = read(STUDY / 'summary.json'); names = list(summary['ice_diagnostic'])
    frame = pd.read_parquet(STUDY / 'ice_predictions.parquet', columns=['station', 'time', 'ice', *['ice_'+c for c in names]])
    tables, signatures = {}, {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / 'src/event_retention.py', STUDY / 'summary.json', STUDY / 'independent_verification.json', STUDY / 'ice_predictions.parquet']}
    for name in names:
        path = STUDY / f'ice_events_{name}.csv'; signatures[str(path.relative_to(ROOT))] = sha(path)
        tables[name] = reconstruct(frame, 'ice_'+name)
        stored = pd.read_csv(path, dtype={'station': str})
        pd.testing.assert_frame_equal(tables[name], stored)
    comparisons = {c: compare_event_retention(tables[BASELINE], tables[c]) for c in names if c != BASELINE}
    freezes = preservation(); OUT.mkdir()
    write(OUT / 'review.json', dict(status='event_identity_review_verified', reviewed_at_utc=datetime.now(timezone.utc).isoformat(),
          comparisons=comparisons, event_tables_independently_reconstructed=len(names), target_events=347,
          criterion_added_after_development_results=True, previous_model_choices_changed=False,
          input_signatures=signatures, assessment_outcomes_used=False, model_promoted=False, old_frozen_files=freezes[0], reserved_frozen_files=freezes[1]))
    for name, result in comparisons.items(): print(name, 'lost/gained', result['lost_events'], result['gained_events'], 'eligible', result['eligible_no_event_loss'])


if __name__ == '__main__': main()
