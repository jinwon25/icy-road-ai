"""저장된 온도 후보를 모델 재추론·별도 지표 계산·입력 서명으로 검산한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.validation import regression_metrics, PROTECTED_STATIONS


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def reference_metrics(frame, column):
    rows = {str(st): regression_metrics(p.road_temp, p[column]) for st, p in frame.groupby('station')}
    return {'pooled': regression_metrics(frame.road_temp, frame[column]), 'stations': rows,
            'station_macro': {m: float(np.mean([r[m] for r in rows.values()])) for m in ['mae', 'rmse', 'bias']},
            'near_freezing': regression_metrics(frame.loc[frame.road_temp.between(-2, 2), 'road_temp'],
                                               frame.loc[frame.road_temp.between(-2, 2), column])}


def compare(expected, actual):
    if set(expected) != set(actual): raise ValueError('Metric schema differs')
    for key in expected:
        a, b = expected[key], actual[key]
        if isinstance(a, dict): compare(a, b)
        elif a is None:
            if b is not None: raise ValueError('Undefined metric changed')
        else: np.testing.assert_allclose(a, b, rtol=0, atol=1e-10)


def reference_choice(reports, candidates, harm):
    base = reports['direct_weather14']; eligible = []
    for c in candidates:
        r = reports[c]
        if r['station_macro']['mae'] >= base['station_macro']['mae'] - 1e-12: continue
        if r['station_macro']['rmse'] >= base['station_macro']['rmse'] - 1e-12: continue
        if any(r['stations'][s]['mae'] > base['stations'][s]['mae'] * (1 + harm) + 1e-12 for s in base['stations']): continue
        if r['near_freezing']['n'] and r['near_freezing']['mae'] > base['near_freezing']['mae'] + 1e-12: continue
        eligible.append(c)
    return min(eligible, key=lambda c: (reports[c]['station_macro']['mae'], reports[c]['station_macro']['rmse'], c)) if eligible else 'direct_weather14'


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--experiment', required=True, type=Path)
    args = parser.parse_args(); out = args.experiment.resolve()
    if not out.is_relative_to((ROOT / 'outputs/private').resolve()): raise ValueError('Private experiment required')
    if (out / 'independent_verification.json').exists(): raise FileExistsError('Preserve prior audit')
    summary = read(out / 'summary.json'); config = read(out / 'experiment_plan.json')
    for rel, digest in summary['files'].items():
        path = (out / rel).resolve()
        if not path.is_relative_to(out) or sha256_file(path) != digest: raise ValueError('Experiment artifact changed')
    for name, r in read(out / 'input_signature.json').items():
        # 실행 당시 소스의 보존본을 검증하며 이후 코드 변경과 구별한다.
        path = out / {'runner': 'analysis_source.py', 'implementation': 'temperature_transfer.py'}.get(name, '') if name in ['runner', 'implementation'] else Path(r['path'])
        if sha256_file(path) != r['sha256']: raise ValueError('Source signature changed: ' + name)
    frame = pd.read_parquet(out / 'development_inputs.parquet')
    if set(frame.station) & PROTECTED_STATIONS or not frame.time.between('2024-11-01', '2025-02-28 23:50').all():
        raise ValueError('Forbidden outcome in experiment')
    results = pd.read_parquet(out / 'outer_predictions.parquet')
    metrics = {c: reference_metrics(results, c) for c in summary['metrics']}
    for c in metrics: compare(metrics[c], summary['metrics'][c])
    groups = read(out / 'groups.json'); fits = read(out / 'fit_receipts.json')
    lookups = {(r['candidate'], tuple(r['forbidden_stations'])): r for r in fits}
    prediction_checks = 0
    with threadpool_limits(limits=2):
        for receipt in fits:
            train = frame.loc[frame.road_temp.notna() & frame.asos_air_temp.notna()
                              & ~frame.station.isin(receipt['forbidden_stations'])]
            if sorted(train.station.unique()) != receipt['training_stations'] or len(train) != receipt['training_rows']:
                raise ValueError('Fit exclusion or training rows changed')
            digest = hashlib.sha256(pd.util.hash_pandas_object(train, index=True).to_numpy().tobytes()).hexdigest()
            if digest != receipt['training_values_sha256']: raise ValueError('Training values changed')
            if sha256_file(out / receipt['model_path']) != receipt['model_sha256']: raise ValueError('Model changed')
        for outer, held in groups.items():
            inner = pd.read_parquet(out / outer / 'inner_oof.parquet')
            if set(inner.station) & set(held): raise ValueError('Outer labels in selection')
            reports = {c: reference_metrics(inner, c) for c in ['direct_weather14', *config['candidates']]}
            decision = read(out / outer / 'decision.json')
            for c in reports: compare(reports[c], decision['inner_reports'][c])
            if reference_choice(reports, config['candidates'], config['maximum_station_harm']) != decision['selected_candidate']:
                raise ValueError('Inner candidate decision differs')
            for queried in [held, *[v for g, v in groups.items() if g != outer]]:
                forbidden = set(held) | set(queried)
                query = frame.loc[frame.station.isin(queried)]
                stored = results if set(queried) == set(held) else inner
                positions = pd.MultiIndex.from_frame(query[['station', 'time']])
                saved = stored.set_index(['station', 'time']).loc[positions]
                for candidate in config['candidates']:
                    receipt = lookups[candidate, tuple(sorted(forbidden))]
                    model = joblib.load(out / receipt['model_path'])
                    p = model.predict(query[receipt['features']])
                    if receipt['residual_anchor']: p += query[receipt['residual_anchor']].to_numpy()
                    p = np.where(query.asos_air_temp.notna(), p, np.nan)
                    np.testing.assert_allclose(saved[candidate], p, rtol=0, atol=1e-12, equal_nan=True)
                    prediction_checks += len(query)
            check = results.loc[results.group.eq(outer)]
            np.testing.assert_allclose(check.selected_temperature, check[decision['selected_candidate']], rtol=0, atol=0, equal_nan=True)
    verification = {'status': 'independent_temperature_audit_passed', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
                    'models': len(fits), 'recomputed_candidate_prediction_values': prediction_checks,
                    'outer_rows': len(results), 'metric_variants': len(metrics), 'inner_decisions': len(groups),
                    'scope': '모델 재추론·독립 집계 검산이며 새 독립 정답 평가는 아니다.',
                    'summary_sha256': sha256_file(out / 'summary.json')}
    with (out / 'independent_verification.json').open('x', encoding='utf-8') as handle:
        json.dump(verification, handle, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == '__main__': main()
