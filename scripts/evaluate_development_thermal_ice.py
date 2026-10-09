"""저장한 첫 겨울 예측에 고정 규칙을 적용해 새 비공개 폴더에 검증 결과를 저장한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.thermal_ice import evaluate_fixed_policies
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions', type=Path, required=True,
                        help='첫 겨울의 기존 그룹 제외 예측·공식 정답·과거 수분 입력 parquet')
    parser.add_argument('--output', type=Path, required=True,
                        help='outputs/private 내부의 존재하지 않는 결과 폴더')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'outputs/private').resolve()):
        parser.error('결과는 outputs/private 내부에만 저장합니다.')
    if output.exists():
        raise FileExistsError('기존 성공·실패 증거를 보존하세요. 새 결과 폴더가 필요합니다.')
    source = args.predictions.resolve()
    metrics, fallbacks, stations, days, events = evaluate_fixed_policies(pd.read_parquet(source))
    output.mkdir(parents=True, exist_ok=False)
    for name, frame in [('station_metrics', stations), ('daily_metrics', days), ('event_metrics', events)]:
        frame.to_csv(output / f'{name}.csv', index=False)
    summary = dict(status='development_fixed_policy_metrics_reproduced',
                   created_at_utc=datetime.now(timezone.utc).isoformat(),
                   source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                   analysis_sha256=hashlib.sha256((ROOT / 'src/thermal_ice.py').read_bytes()).hexdigest(),
                   scope='Repeated first-winter development; not independent or official performance',
                   official_daily_score=False, model_selected=None, new_fit=False,
                   reserved_or_protected_outcomes_used=False, metrics=metrics, fallback_rows=fallbacks)
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'status': summary['status'], 'output': str(output), 'metrics': metrics}, ensure_ascii=False))


if __name__ == '__main__':
    main()
