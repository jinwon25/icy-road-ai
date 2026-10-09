"""고정 분류기의 DSM 대체 구간 출력을 저장한다. 정확도가 검증된 위험도로 사용하지 않는다."""
import json
import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.frozen_assessment import verify_freeze


def main():
    frozen = verify_freeze(ROOT)
    private = ROOT / 'outputs/private'; out = private / 'segment_ice_exploratory'
    out.mkdir(exist_ok=True)
    source = private / 'segment_inference_v1'
    audit = json.loads((source / 'audit.json').read_text(encoding='utf-8'))
    assert audit['status'] == 'all_segments_verified'
    environment = pd.read_csv(private / 'spatial/environment_features/segment_environment_inventory.csv')
    model = joblib.load(private / 'model_candidates/ice_thermal_v1/ice_hgb.joblib')
    card = json.loads((private / 'model_candidates/ice_thermal_v1/model_card.json').read_text(encoding='utf-8'))
    signature = {'freeze': sha256_file(private / 'frozen_assessment_v1/freeze.json'),
                 'temperature_audit': sha256_file(source / 'audit.json'),
                 'environment': sha256_file(private / 'spatial/environment_features/segment_environment_inventory.csv'),
                 'runner': sha256_file(Path(__file__))}
    signature_path = out / 'input_signature.json'
    if signature_path.exists() and json.loads(signature_path.read_text(encoding='utf-8')) != signature:
        raise ValueError('Changed exploratory inference inputs; preserve existing outputs')
    signature_path.write_text(json.dumps(signature, indent=2), encoding='utf-8')
    records = []
    with threadpool_limits(limits=2):
        for index, row in enumerate(environment.itertuples(), 1):
            folder = out / row.segment_id; folder.mkdir(exist_ok=True)
            if (folder / 'summary.json').exists():
                records.append(json.loads((folder / 'summary.json').read_text(encoding='utf-8'))); continue
            features = pd.read_parquet(source / row.segment_id / 'features.parquet')
            # 정확한 도로면 고도를 확보하지 못했다. 사전 개발 진단한 DSM 대체를 명시한다.
            if not np.isfinite(row.dsm_elevation_m): raise ValueError('Missing DSM proxy')
            features['elevation_m'] = row.dsm_elevation_m
            score = model.predict_proba(features[card['feature_names']])[:, 1]
            result = features[['station', 'time']].rename(columns={'station': 'segment_id'}).copy()
            result['ice_score_dsm_proxy'] = score
            result['predicted_ice_dsm_proxy'] = (score >= frozen['ice_threshold']).astype(int)
            result.to_parquet(folder / 'predictions.parquet', index=False, compression='zstd')
            result.to_csv(folder / 'ice_10min_exploratory.csv.gz', index=False, encoding='utf-8-sig', compression='gzip')
            record = {'segment_id': row.segment_id, 'rows': len(result), 'score_mean': float(score.mean()),
                      'score_max': float(score.max()), 'predicted_ice_slots': int(result.predicted_ice_dsm_proxy.sum()),
                      'height_proxy_m': float(row.dsm_elevation_m), 'height_source': 'Copernicus DSM, not verified road elevation',
                      'threshold': frozen['ice_threshold'], 'predictions_sha256': sha256_file(folder / 'predictions.parquet')}
            (folder / 'summary.json').write_text(json.dumps(record, indent=2), encoding='utf-8'); records.append(record)
            if index % 50 == 0: print(f'Exploratory classification {index}/467', flush=True)
    assert len(records) == 467 and sum(r['rows'] for r in records) == 16139520
    pd.DataFrame(records).to_csv(out / 'segment_ice_summary.csv', index=False, encoding='utf-8-sig')
    summary = {'status': 'exploratory_DSM_transfer_failed_classifier_not_operational_risk', 'segments': len(records),
               'rows': sum(r['rows'] for r in records), 'signature': signature, 'threshold': frozen['ice_threshold'],
               'limitations': ['Fixed classifier failed protected-station Ice detection; these outputs are not a reliable warning system.',
                              'DSM proxy differs from native station elevation. Prior development diagnostic showed increased false alarms.',
                              'Uncalibrated class-weighted model score is not an Ice or accident probability.',
                              'Do not rank or assign validated risk grades from these outputs.',
                              'No model or threshold was changed after the frozen assessment.']}
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('status', 'segments', 'rows')}), flush=True)


if __name__ == '__main__': main()
