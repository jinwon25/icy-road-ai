"""사건 수의 순증가에 가려지는 기존 결빙 사건 누락을 식별한다."""
import numpy as np
import pandas as pd
from src.method_blending import ALLOWED


def compare_event_retention(baseline, candidate):
    columns = ['station', 'start_kst', 'slots', 'detected_slots']
    for f in [baseline, candidate]:
        if not set(columns) <= set(f) or f.duplicated(['station', 'start_kst']).any() or not set(f.station) <= ALLOWED:
            raise ValueError('Unique allowed development events required')
        t = pd.to_datetime(f.start_kst)
        if t.isna().any() or t.dt.tz is not None or not (t.ge('2024-11-01') & t.lt('2025-03-01')).all():
            raise ValueError('First winter KST event identities required')
        values = f[['slots', 'detected_slots']].to_numpy(float)
        if not np.isfinite(values).all() or not np.equal(values, np.floor(values)).all() or not (values[:, 0] > 0).all() or not ((values[:, 1] >= 0) & (values[:, 1] <= values[:, 0])).all():
            raise ValueError('Valid integer event lengths and detections required')
    b = baseline[columns].set_index(['station', 'start_kst']).sort_index()
    c = candidate[columns].set_index(['station', 'start_kst']).sort_index()
    if not b.index.equals(c.index) or not b.slots.equals(c.slots):
        raise ValueError('Exactly the same target event identities required')
    old, new = b.detected_slots.gt(0), c.detected_slots.gt(0)
    lost, gained = old & ~new, ~old & new
    details = b[['slots']].copy(); details['baseline_detected_slots'] = b.detected_slots
    details['candidate_detected_slots'] = c.detected_slots
    return dict(events=len(b), baseline_detected=int(old.sum()), candidate_detected=int(new.sum()),
                lost_events=int(lost.sum()), gained_events=int(gained.sum()), retained_events=int((old & new).sum()),
                lost_single_slot_events=int((lost & b.slots.eq(1)).sum()), eligible_no_event_loss=bool(~lost.any()),
                lost=details.loc[lost].reset_index().to_dict('records'), gained=details.loc[gained].reset_index().to_dict('records'))
