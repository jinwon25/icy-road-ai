"""개봉을 완료한 평균 후보의 실패를 기술한다. 모델·정답·설정을 바꾸지 않는다."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.fresh_station_validation import verify_seal, old_freezes


def main():
    out = ROOT / 'outputs/private/temperature_mean_blind_20261010_v1'
    audit = json.loads((out / 'independent_verification.json').read_text(encoding='utf-8'))
    if audit['status'] != 'independent_equal_mean_blind_audit_passed' or sha(out / 'summary.json') != audit['summary_sha256']:
        raise ValueError('Completed audited evaluation required')
    seal = verify_seal(out); target = out / 'failure_review'; target.mkdir(exist_ok=False)
    frame = pd.read_parquet(out / 'evaluation.parquet')
    rows, bins, states = [], [], []
    for station, part in frame.groupby('station'):
        valid = part.ice.isin([0, 1]); positive = part.ice.eq(1); original = part.original_ice.eq(1)
        base, mean = part.thermal_weather14.eq(1), part.thermal_equal_mean.eq(1)
        rows.append(dict(station=station, planned_rows=len(part), defined_state_rows=int(valid.sum()),
            undefined_state_rows=int((~valid).sum()), ice_rows=int(positive.sum()),
            ice_with_observed_temp_gt_zero=int((positive & part.road_temp.gt(0)).sum()),
            ice_with_observed_temp_le_zero=int((positive & part.road_temp.le(0)).sum()),
            ice_with_missing_observed_temp=int((positive & ~np.isfinite(part.road_temp)).sum()),
            extra_false_alarms_vs_weather14=int((valid & ~positive & ~base & mean).sum()),
            removed_false_alarms_vs_weather14=int((valid & ~positive & base & ~mean).sum()),
            gained_ice_vs_weather14=int((positive & ~base & mean).sum()),
            lost_ice_vs_weather14=int((positive & base & ~mean).sum()),
            gained_ice_vs_original=int((positive & ~original & mean).sum()),
            lost_ice_vs_original=int((positive & original & ~mean).sum())))
        for state, grouped in part.groupby('state_raw', dropna=False):
            states.append(dict(station=station, state_raw=str(state), rows=len(grouped)))
        categories = pd.cut(part.road_temp, [-np.inf, -2, 0, 2, np.inf], labels=['<=-2', '(-2,0]', '(0,2]', '>2'])
        for category in categories.cat.categories:
            selected = part.loc[categories.eq(category) & valid]
            for policy in ['original_ice', 'thermal_weather14', 'thermal_equal_mean']:
                ice, pred = selected.ice.eq(1), selected[policy].eq(1)
                bins.append(dict(station=station, observed_temperature_bin=str(category), policy=policy,
                    n=len(selected), ice_rows=int(ice.sum()), tp=int((ice & pred).sum()),
                    fp=int((~ice & pred).sum()), fn=int((ice & ~pred).sum())))
    for name, values in [('station_failures.csv', rows), ('observed_temperature_bins.csv', bins), ('raw_state_counts.csv', states)]:
        pd.DataFrame(values).to_csv(target / name, index=False, encoding='utf-8-sig')
    result = dict(status='post_opening_descriptive_failure_review', created_at_utc=datetime.now(timezone.utc).isoformat(),
        summary_sha256=sha(out / 'summary.json'), evaluation_sha256=sha(out / 'evaluation.parquet'), source_sha256=sha(__file__),
        stations=rows, candidate_retuned=False, labels_reclassified_or_dropped=False,
        independent_new_validation_created=False, sensor_error_cause_established=False,
        files={p.name: sha(p) for p in target.iterdir() if p.is_file()})
    verify_seal(out)
    if old_freezes() != (seal['original_frozen_files'], seal['reserved_frozen_files']):
        raise ValueError('Existing frozen files changed')
    (target / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result['stations'], ensure_ascii=False))


if __name__ == '__main__':
    main()
