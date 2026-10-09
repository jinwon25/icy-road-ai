"""감사 완료한 첫 겨울 후보의 순위와 점수 척도를 집계한다. 재선택은 없다."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.thermal_ice import validate_development


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(); folder = args.experiment.resolve()
    output = args.output.resolve() if args.output else folder / 'ranking_diagnostics.json'
    if not folder.is_relative_to((ROOT / 'outputs/private').resolve()) or not output.is_relative_to((ROOT / 'outputs/private').resolve()):
        parser.error('Only private local experiments and outputs allowed')
    if output.exists():
        raise FileExistsError('Preserve previous diagnostics; choose a new output file')
    audit = json.loads((folder / 'independent_verification.json').read_text('utf-8'))
    seal = json.loads((folder / 'prediction_seal.json').read_text('utf-8'))
    if audit['status'] != 'passed':
        raise ValueError('Independent audit required')
    path = folder / 'outer_predictions.parquet'
    if hashlib.sha256(path.read_bytes()).hexdigest() != seal['sha256']:
        raise ValueError('Changed prediction population')
    data = validate_development(pd.read_parquet(path)); groups = []; scales = []
    for group, part in data[data.ice.notna()].groupby('group'):
        row = dict(group=group, n=len(part), ice=int(part.ice.sum()), prevalence=float(part.ice.mean()))
        for candidate in ['baseline', 'binary_thermal_weather', 'joint_surface_state']:
            row[candidate + '_ap'] = float(average_precision_score(part.ice, part[candidate + '_score']))
        groups.append(row)
        for candidate in ['binary_thermal_weather', 'joint_surface_state']:
            score = part[candidate + '_score']; positive = score[part.ice.eq(1)]; negative = score[part.ice.eq(0)]
            scales.append(dict(group=group, candidate=candidate, threshold=float(part[candidate + '_threshold'].iloc[0]),
                               positive_median_score=float(positive.median()), positive_p95_score=float(positive.quantile(.95)),
                               negative_median_score=float(negative.median()), negative_p95_score=float(negative.quantile(.95))))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(groups=groups, pooled_constant_ap=float(data.ice.mean()),
                                     score_note='Weighted scores from different outer models are not calibrated risk probabilities.',
                                     score_scales=scales), ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print('순위·척도 집계 저장:', output.relative_to(ROOT))


if __name__ == '__main__':
    main()
