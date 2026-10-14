"""개발 후보4모델·하루 캐시만 담은 비공개 로컬 재현 묶음을 만들고 실행한다."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import catboost
import joblib
import numpy as np
import pandas as pd
import pyarrow
import sklearn
import threadpoolctl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.joint_surface import WEATHER, FEATURES

PRIVATE = ROOT / 'outputs/private'
OUT = PRIVATE / 'offline_review_bundle_20261013_v1'

RUNNER = '''"""미채택 개발 후보의 오프라인 재현 예제. 최종 제출·공식 성능이 아니다."""
import json
from pathlib import Path
import hashlib
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from offline_runtime import deny_network

HERE = Path(__file__).resolve().parent
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
manifest = json.loads((HERE / 'bundle_manifest.json').read_text('utf-8'))
for name, digest in manifest['files'].items():
    assert sha(HERE / name) == digest, name
with deny_network() as attempts, threadpool_limits(limits=2):
    weather = pd.read_parquet(HERE / 'data/weather_day.parquet')
    classifier = pd.read_parquet(HERE / 'data/classifier_day.parquet')
    expected = pd.read_parquet(HERE / 'data/reference_predictions.parquet')
    temperature = np.zeros(len(weather))
    for name in manifest['temperature_components']:
        model = joblib.load(HERE / 'model' / (name+'.joblib'))
        temperature += model.predict(weather[list(model.feature_names_in_)])/3
    model = joblib.load(HERE / 'model/catboost400.joblib')
    score = model.predict_proba(classifier[manifest['classifier_features']])[:, list(model.classes_).index(1)]
    lower, upper = temperature-manifest['radius'], temperature+manifest['radius']
    for actual, name in [(temperature, 'estimated_road_temp_c'), (lower, 'empirical_lower_c'), (upper, 'empirical_upper_c'), (score, 'uncalibrated_catboost_score')]:
        np.testing.assert_allclose(actual, expected[name], atol=1e-10, rtol=0)
assert attempts == []
print(json.dumps({'status': 'isolated_local_bundle_replay_passed', 'rows': len(weather), 'outputs_verified': len(weather)*4, 'models_loaded': 4, 'network_attempts': len(attempts), 'new_training': False, 'final_submission_model': False}))
'''


def main():
    if OUT.exists():
        raise FileExistsError('Preserve previous review bundle')
    proof = PRIVATE / 'offline_inference_20261013_v1'
    receipt = json.loads((proof / 'verification_receipt.json').read_text('utf-8'))
    assert receipt['status'] == 'offline_inference_replay_passed' and receipt['network_attempts'] == 0 and receipt['verified_prediction_values'] == 1008
    for rel, digest in receipt['input_signatures'].items():
        assert sha(ROOT / rel) == digest, rel
    OUT.mkdir(); (OUT / 'model').mkdir(); (OUT / 'data').mkdir()
    signatures = {str(Path(__file__).relative_to(ROOT)): sha(Path(__file__)), str((proof / 'verification_receipt.json').relative_to(ROOT)): sha(proof / 'verification_receipt.json')}
    candidates = receipt['temperature_components']
    registry = json.loads((PRIVATE / 'method_blending_20261010_v2/reused_model_receipts.json').read_text('utf-8'))
    for name in candidates:
        r = next(r for r in registry if r['candidate'] == name and set(r['forbidden_stations']) == {'12207', '12408'})
        path = ROOT / r['model_path']; signatures[str(path.relative_to(ROOT))] = sha(path)
        shutil.copy2(path, OUT / 'model' / (name+'.joblib'))
    cat_path = PRIVATE / 'ice_methodology_20261010_v1/contexts/seohaean_seocheon/catboost400.joblib'
    signatures[str(cat_path.relative_to(ROOT))] = sha(cat_path); shutil.copy2(cat_path, OUT / 'model/catboost400.joblib')
    times = pd.date_range(receipt['date_kst'], periods=144, freq='10min')
    selected = lambda f: f.station.eq(receipt['station']) & f.time.isin(times)
    path = PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet'
    data = pd.read_parquet(path, columns=['station', 'time', *WEATHER]); data = data.loc[selected(data)].sort_values('time').reset_index(drop=True)
    assert len(data) == 144 and data.asos_air_temp.notna().all()
    data.to_parquet(OUT / 'data/weather_day.parquet', index=False)
    path = PRIVATE / 'ice_methodology_20261010_v1/contexts/seohaean_seocheon/query_inputs.parquet'
    classifier = pd.read_parquet(path, columns=['station', 'time', *FEATURES]); classifier = classifier.loc[selected(classifier)].sort_values('time').reset_index(drop=True)
    assert classifier[['station', 'time']].equals(data[['station', 'time']])
    classifier.to_parquet(OUT / 'data/classifier_day.parquet', index=False)
    shutil.copy2(proof / 'development_day_inference.parquet', OUT / 'data/reference_predictions.parquet')
    assert sha(OUT / 'data/reference_predictions.parquet') == receipt['result_sha256']
    shutil.copy2(ROOT / 'src/offline_runtime.py', OUT / 'offline_runtime.py')
    (OUT / 'run_offline.py').write_text(RUNNER, encoding='utf-8')
    packages = {'catboost': catboost.__version__, 'joblib': joblib.__version__, 'numpy': np.__version__, 'pandas': pd.__version__, 'pyarrow': pyarrow.__version__, 'scikit-learn': sklearn.__version__, 'threadpoolctl': threadpoolctl.__version__}
    (OUT / 'requirements.txt').write_text('\n'.join(f'{k}=={v}' for k, v in packages.items())+'\n', encoding='utf-8')
    (OUT / 'README.md').write_text('''# 개발 후보의 오프라인 재현 예제

2024-12-15 KST 개발 지점12207의144행에서 저장 모델4개를 재실행합니다. 최종 대회 제출 모델·독립 평가·공식 점수가 아닙니다.

의존성을 먼저 설치한 뒤 이 폴더에서 `python -X utf8 run_offline.py`를 실행합니다. 실행 중 새 관측 다운로드·외부 분석/예측 서비스·인증키는 필요하지 않습니다. Python DNS와 주요 소켓 접속을 차단해 호출 시도가 있으면 실패합니다. OS 전체 네트워크 격리 보장은 아닙니다.

온도는 기상12/MSE300/MAE300의 고정 평균, 범위는 다른 개발 그룹 OOF의 경험적90분위수입니다. CatBoost는 기존 교차 추정 온도 입력을 유지한 미채택 연구 후보입니다. 점수는 보정된 결빙 확률이 아니며 범위는90% 보장·안전 판정이 아닙니다. 과거 평가 지점이나 보호 지점의 정답은 포함하지 않습니다.

`data/`는 하루 기상 입력·분류 입력·저장 예측 대조값, `model/`은4개 저장 모델입니다. 상태·실제 노면온도 정답·API 키·원본ZIP은 포함하지 않습니다. 이 예제는 참가 권한 내 로컬 검토용이며 외부로 전송하거나 공개하지 않았습니다. 출처·이용 조건과 공식 제출 범위는 원본 프로젝트 문서를 함께 확인합니다.
''', encoding='utf-8')
    radius = json.loads((PRIVATE / 'temperature_uncertainty_20261010_v1/calibrations.json').read_text('utf-8'))[receipt['group']][receipt['temperature_blend']]['radius']
    manifest = dict(status='private_local_development_review_bundle', built_at_utc=datetime.now(timezone.utc).isoformat(), python=platform.python_version(), station=receipt['station'], date_kst=receipt['date_kst'], rows=144,
                    temperature_components=candidates, classifier_features=FEATURES, radius=radius, source_proof_sha256=sha(proof / 'verification_receipt.json'),
                    input_signatures=signatures, external_prediction_api_required=False, final_submission_model=False,
                    files={p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()})
    (OUT / 'bundle_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    result = subprocess.run([sys.executable, '-X', 'utf8', str(OUT / 'run_offline.py')], cwd=OUT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (OUT / 'replay.log').write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError('Separate interpreter replay failed; preserve failure log')
    verification = dict(status='private_bundle_replay_passed', returncode=result.returncode, checked_at_utc=datetime.now(timezone.utc).isoformat(),
                        total_source_files=len(manifest['files']), total_bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),
                        manifest_sha256=sha(OUT / 'bundle_manifest.json'), replay_log_sha256=sha(OUT / 'replay.log'), assessment_outcomes_used=False, submitted=False)
    (OUT / 'verification.json').write_text(json.dumps(verification, indent=2), encoding='utf-8'); print(result.stdout.decode('utf-8')); print(verification)


if __name__ == '__main__':
    main()
