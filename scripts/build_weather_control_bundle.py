"""온도·결빙·사건 보존 개발 기준을 통과한 고정2모델 평균의 로컬 재현."""
from datetime import datetime, timezone
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import joblib
import numpy as np
import pandas as pd
import pyarrow
import sklearn
import threadpoolctl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import read, write
from src.weather_distance_ablation import DISTANCE_FREE_FEATURES

PRIVATE = ROOT / 'outputs/private'
STUDY = PRIVATE / 'weather_memory_controls_20261013_v1'
OUT = PRIVATE / 'weather_control_offline_bundle_20261013_v1'
NAMES = ['nohistory12_mse300', 'nohistory12_mae300']

RUNNER = '''"""개발 고정2종 평균의 재현. 독립·공식 평가나 최종 제출 모델이 아니다."""
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from offline_runtime import deny_network

HERE = Path(__file__).resolve().parent
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
manifest = json.loads((HERE / 'bundle_manifest.json').read_text('utf-8'))
for name, digest in manifest['files'].items(): assert sha(HERE / name) == digest, name
with deny_network() as attempts, threadpool_limits(limits=2):
    weather = pd.read_parquet(HERE / 'data/weather_day.parquet')
    expected = pd.read_parquet(HERE / 'data/reference_predictions.parquet')
    assert len(weather) == 144 and weather[['station', 'time']].equals(expected[['station', 'time']])
    assert not {'road_temp', 'ice', 'state_raw'}.intersection(weather.columns)
    values = {}
    for name in manifest['components']:
        model = joblib.load(HERE / 'model' / (name+'.joblib'))
        values[name] = model.predict(weather[list(model.feature_names_in_)])
    values['equal_nohistory_pair'] = sum(values.values())/2
    temperature = values['equal_nohistory_pair']
    water = weather[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy()
    assert np.isfinite(temperature).all() and not np.isnan(water).all(axis=1).any()
    values['ice_equal_nohistory_pair'] = ((temperature <= 0) & ((water[:, 0] >= temperature) | (water[:, 1] > 0) | (water[:, 2] > 0))).astype(int)
    for name, value in values.items(): np.testing.assert_allclose(value, expected[name], atol=1e-10, rtol=0)
assert attempts == []
print(json.dumps({'status': 'weather_control_bundle_replay_passed', 'rows': len(weather), 'models_loaded': 2, 'prediction_values_verified': len(weather)*len(values), 'network_attempts': len(attempts), 'new_model_fits': 0, 'final_submission_model': False}))
'''


def main():
    if OUT.exists(): raise FileExistsError('Preserve control bundle')
    tradeoff_path = PRIVATE / 'weather_memory_tradeoffs_20261013_v1/review.json'
    review = read(tradeoff_path); assert review['comparisons']['equal_nohistory_pair']['combined_eligible']
    audit = read(STUDY / 'independent_verification.json'); assert audit['summary_sha256'] == sha(STUDY / 'summary.json')
    for rel, digest in read(STUDY / 'input_signatures.json').items(): assert sha(ROOT / rel) == digest
    OUT.mkdir(); (OUT / 'model').mkdir(); (OUT / 'data').mkdir()
    pinned = [Path(__file__), ROOT / 'src/offline_runtime.py', STUDY / 'summary.json', STUDY / 'independent_verification.json',
              STUDY / 'fit_receipts.json', STUDY / 'ice_predictions.parquet', tradeoff_path,
              PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet']
    for name in NAMES:
        r = next(r for r in read(STUDY / 'fit_receipts.json') if r['candidate'] == name and r['excluded_groups'] == ['seohaean_seocheon'])
        path = STUDY / r['model_path']; assert sha(path) == r['model_sha256']; pinned.append(path); shutil.copy2(path, OUT / 'model' / (name+'.joblib'))
    date = pd.Timestamp('2024-12-15'); columns = ['station', 'time', *DISTANCE_FREE_FEATURES, 'rain15_max_3h', 'asos_snow_cm']
    raw = pd.read_parquet(PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet', columns=columns)
    query = raw.loc[raw.station.eq('12207') & raw.time.dt.normalize().eq(date)].sort_values('time').reset_index(drop=True)
    assert len(query) == 144; query.to_parquet(OUT / 'data/weather_day.parquet', index=False)
    expected = pd.read_parquet(STUDY / 'ice_predictions.parquet', columns=['station', 'time', *NAMES, 'equal_nohistory_pair', 'ice_equal_nohistory_pair'])
    expected = expected.loc[expected.station.eq('12207') & expected.time.dt.normalize().eq(date)].sort_values('time').reset_index(drop=True)
    assert expected[['station', 'time']].equals(query[['station', 'time']]); expected.to_parquet(OUT / 'data/reference_predictions.parquet', index=False)
    shutil.copy2(ROOT / 'src/offline_runtime.py', OUT / 'offline_runtime.py'); (OUT / 'run_offline.py').write_text(RUNNER, encoding='utf-8')
    versions = {'joblib': joblib.__version__, 'numpy': np.__version__, 'pandas': pd.__version__, 'pyarrow': pyarrow.__version__, 'scikit-learn': sklearn.__version__, 'threadpoolctl': threadpoolctl.__version__}
    (OUT / 'requirements.txt').write_text('\n'.join(f'{k}=={v}' for k, v in versions.items())+'\n', encoding='utf-8')
    (OUT / 'README.md').write_text('''# 고정 기상12 모델2종 평균의 로컬 재현

거리 없는 기상12개 입력으로300회 학습한 MSE/MAE 모델의1:1 평균을 재현합니다. 첫 겨울 개발9곳에서 온도·결빙·기존 사건 보존 기준을 통과한 연구 후보이며 독립·공식 평가·최종 제출 모델이 아닙니다. 다른 지점·겨울의 일반화를 입증하지 않습니다.

이 묶음은 학습에서12207·12408 전체를 제외한 저장2모델과2024-12-15 KST 개발12207의144행 기상·예측 대조값을 포함합니다. 실제 노면온도·실제 상태·원본ZIP·API 키는 없습니다. 결빙 출력은0°C·수분의 고정 물리 규칙이며 보정된 결빙 확률이나 도로 안전 판정이 아닙니다. 이 하루의 입력 누락이 없음을 검사하며 일반 결측 환경의 기존 fallback 모델을 모두 포장한 것은 아닙니다.

의존성을 먼저 설치하고 이 폴더에서 `python -X utf8 run_offline.py`를 실행합니다. 저장2모델·576개 예측/판정이 원래 결과와 일치하고 DNS·주요 소켓 접속 시도가0임을 확인합니다. 외부 분석/예측 서비스·다운로드·새 학습은 필요하지 않습니다. OS 전체 네트워크 격리 보장은 아닙니다. 참가 권한 내 로컬 검토용이며 원본 프로젝트의 출처·공개 조건을 함께 확인합니다.
''', encoding='utf-8')
    manifest = dict(status='private_weather_control_review_bundle', built_at_utc=datetime.now(timezone.utc).isoformat(), python=platform.python_version(), station='12207', date_kst=str(date.date()),
          rows=144, components=NAMES, weights=[.5, .5], input_signatures={str(p.relative_to(ROOT)): sha(p) for p in pinned},
          final_submission_model=False, external_prediction_api_required=False,
          files={p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()})
    write(OUT / 'bundle_manifest.json', manifest)
    result = subprocess.run([sys.executable, '-X', 'utf8', str(OUT / 'run_offline.py')], cwd=OUT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (OUT / 'replay.log').write_bytes(result.stdout)
    if result.returncode: raise RuntimeError('Preserve failed replay')
    write(OUT / 'verification.json', dict(status='weather_control_private_bundle_verified', returncode=result.returncode,
          checked_at_utc=datetime.now(timezone.utc).isoformat(), source_files=len(manifest['files']), source_bytes=sum((OUT / n).stat().st_size for n in manifest['files']),
          manifest_sha256=sha(OUT / 'bundle_manifest.json'), replay_log_sha256=sha(OUT / 'replay.log'), submitted=False, assessment_outcomes_used=False))
    print(result.stdout.decode('utf-8')); print(read(OUT / 'verification.json'))


if __name__ == '__main__': main()
