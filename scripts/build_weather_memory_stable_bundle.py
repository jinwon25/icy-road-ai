"""고정 기상 이력 결합5모델과12시간 준비 입력의 비공개 오프라인 재현 묶음."""
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
from src.temperature_transfer import WEATHER_FEATURES
from src.weather_memory_temperature_stable import BASELINE, CANDIDATES, FEATURES
from scripts.evaluate_method_blending import read, write

PRIVATE = ROOT / 'outputs/private'
STUDY = PRIVATE / 'weather_memory_temperature_20261013_v2'
OUT = PRIVATE / 'weather_memory_offline_bundle_20261013_v2'

RUNNER = '''"""기상 이력 연구 후보의 재현 예제. 실제 정답·최종 제출 모델을 포함하지 않는다."""
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
    raw = pd.read_parquet(HERE / 'data/weather_with_warmup.parquet')
    expected_features = pd.read_parquet(HERE / 'data/reference_features.parquet')
    expected = pd.read_parquet(HERE / 'data/reference_predictions.parquet')
    assert len(raw) == 216 and raw.station.nunique() == 1 and raw.time.diff().iloc[1:].eq(pd.Timedelta(minutes=10)).all()
    assert not {'road_temp', 'ice', 'state_raw'}.intersection(raw.columns)
    x = raw.copy(); times = raw.time.to_numpy(dtype='datetime64[ns]'); right = np.arange(len(raw))
    for c in manifest['history_columns']:
        v = raw[c].to_numpy(float); valid = np.isfinite(v)
        integers = np.rint(np.where(valid, v, 0.)*1_000_000).astype(np.int64)
        sums = np.r_[np.int64(0), np.cumsum(integers, dtype=np.int64)]
        counts = np.r_[np.int64(0), np.cumsum(valid, dtype=np.int64)]
        for minutes in [60, 180, 720]:
            left = np.searchsorted(times, times-np.timedelta64(minutes, 'm'), side='left')
            n = counts[right]-counts[left]
            mean = np.divide(sums[right]-sums[left], n*1_000_000, out=np.full(len(raw), np.nan), where=n >= np.ceil(.8*minutes/10))
            x[f'{c}_past_mean_{minutes}m'] = np.round(mean, 6)
        for minutes in [60, 180]:
            wanted = times-np.timedelta64(minutes, 'm'); ids = np.searchsorted(times, wanted)
            exact = (ids < len(raw)) & (times[np.minimum(ids, len(raw)-1)] == wanted)
            usable = exact & valid & valid[np.minimum(ids, len(raw)-1)]
            delta = np.full(len(raw), np.nan); delta[usable] = (integers[usable]-integers[ids[usable]])/1_000_000
            x[f'{c}_change_{minutes}m'] = delta
    query = x.loc[x.time.dt.normalize().eq(pd.Timestamp(manifest['date_kst']))].reset_index(drop=True)
    assert len(query) == 144 and expected_features[['station', 'time']].equals(query[['station', 'time']])
    np.testing.assert_allclose(query[manifest['memory_features']], expected_features[manifest['memory_features']], atol=0, rtol=0, equal_nan=True)
    values = {}
    for name in manifest['components']:
        model = joblib.load(HERE / 'model' / (name+'.joblib'))
        values[name] = model.predict(query[list(model.feature_names_in_)])
    baseline = sum(values[n] for n in manifest['baseline_components'])/3
    pair = (values['memory12_mse300']+values['memory12_mae300'])/2
    output = {'equal_distance_mse_mae300': baseline, 'memory12_mse300': values['memory12_mse300'], 'memory12_mae300': values['memory12_mae300'], 'equal_memory_pair': pair, 'equal_trio_memory': (baseline+pair)/2}
    for name, radius in manifest['global_radii'].items():
        output[name+'_global_lower'] = output[name]-radius
        output[name+'_global_upper'] = output[name]+radius
    assert set(output) == set(expected)-{'station', 'time'}
    for name, v in output.items(): np.testing.assert_allclose(v, expected[name], atol=1e-10, rtol=0)
assert attempts == []
print(json.dumps({'status': 'weather_memory_bundle_replay_passed', 'input_rows_with_warmup': len(raw), 'query_rows': len(query), 'models_loaded': 5, 'feature_values_verified': len(query)*len(manifest['memory_features']), 'prediction_values_verified': len(query)*len(output), 'network_attempts': len(attempts), 'new_model_fits': 0, 'final_submission_model': False}))
'''


def main():
    if OUT.exists(): raise FileExistsError('Preserve review bundle')
    audit = read(STUDY / 'independent_verification.json')
    assert audit['status'] == 'independent_weather_memory_temperature_audit_passed' and audit['summary_sha256'] == sha(STUDY / 'summary.json')
    for rel, digest in read(STUDY / 'input_signatures.json').items(): assert sha(ROOT / rel) == digest
    OUT.mkdir(); (OUT / 'model').mkdir(); (OUT / 'data').mkdir()
    pinned = [Path(__file__), ROOT / 'src/offline_runtime.py', ROOT / 'src/weather_memory_temperature_stable.py',
              ROOT / 'src/weather_memory_temperature.py', STUDY / 'summary.json', STUDY / 'independent_verification.json',
              STUDY / 'fit_receipts.json', STUDY / 'history_inputs.parquet', STUDY / 'outer_predictions.parquet', STUDY / 'calibrations.json',
              PRIVATE / 'method_blending_20261010_v2/reused_model_receipts.json', PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet']
    old_names = ['weather12_no_distance', 'weather_mse300', 'weather_mae300']; new_names = ['memory12_mse300', 'memory12_mae300']
    registry = read(PRIVATE / 'method_blending_20261010_v2/reused_model_receipts.json')
    for name in old_names:
        r = next(r for r in registry if r['candidate'] == name and set(r['forbidden_stations']) == {'12207', '12408'})
        path = ROOT / r['model_path']; assert sha(path) == r['model_sha256']; pinned.append(path)
        shutil.copy2(path, OUT / 'model' / (name+'.joblib'))
    for name in new_names:
        r = next(r for r in read(STUDY / 'fit_receipts.json') if r['candidate'] == name and r['excluded_groups'] == ['seohaean_seocheon'])
        path = STUDY / r['model_path']; assert sha(path) == r['model_sha256']; pinned.append(path)
        shutil.copy2(path, OUT / 'model' / (name+'.joblib'))
    data = pd.read_parquet(PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet', columns=['station', 'time', *WEATHER_FEATURES])
    date = pd.Timestamp('2024-12-15'); mask = data.station.eq('12207') & data.time.ge(date-pd.Timedelta(hours=12)) & data.time.lt(date+pd.Timedelta(days=1))
    raw = data.loc[mask].sort_values('time').copy(); assert len(raw) == 216
    raw.to_parquet(OUT / 'data/weather_with_warmup.parquet', index=False)
    history = pd.read_parquet(STUDY / 'history_inputs.parquet').loc[raw.index]
    expanded = pd.concat([raw, history], axis=1); query = expanded.loc[expanded.time.ge(date), ['station', 'time', *FEATURES]]
    assert len(query) == 144
    query.to_parquet(OUT / 'data/reference_features.parquet', index=False)
    range_names = [BASELINE, 'equal_trio_memory']
    columns = ['station', 'time', BASELINE, *CANDIDATES]+[n+'_global_'+side for n in range_names for side in ['lower', 'upper']]
    expected = pd.read_parquet(STUDY / 'outer_predictions.parquet', columns=columns)
    expected = expected.loc[expected.station.eq('12207') & expected.time.dt.normalize().eq(date)].sort_values('time')
    assert expected[['station', 'time']].reset_index(drop=True).equals(query[['station', 'time']].reset_index(drop=True))
    expected.to_parquet(OUT / 'data/reference_predictions.parquet', index=False)
    shutil.copy2(ROOT / 'src/offline_runtime.py', OUT / 'offline_runtime.py'); (OUT / 'run_offline.py').write_text(RUNNER, encoding='utf-8')
    versions = {'joblib': joblib.__version__, 'numpy': np.__version__, 'pandas': pd.__version__, 'pyarrow': pyarrow.__version__, 'scikit-learn': sklearn.__version__, 'threadpoolctl': threadpoolctl.__version__}
    (OUT / 'requirements.txt').write_text('\n'.join(f'{k}=={v}' for k, v in versions.items())+'\n', encoding='utf-8')
    (OUT / 'README.md').write_text('''# 기상 이력 온도 후보의 오프라인 재현

개발12207 지점의2024-12-15 KST 하루144행과 앞선12시간72행을 사용해 저장5모델을 재실행합니다. 기존3종 평균과 기상 이력2종 평균을1:1로 결합하는 연구 후보입니다. 최종 제출 모델·독립 평가·공식 점수가 아닙니다.

표시 시점보다 엄격히 앞선1·3·12시간 기상 평균과 정확한1·3시간 변화량30개를 다시 계산합니다. 기상값을 소수6자리 정수로 바꿔 정수 누적합을 사용하고 평균도 소수6자리로 처리합니다. 전체 겨울과 최소12시간 준비 입력의42개 특징6,048값은 비트 단위로 같고 예측/경계1,296값은 허용오차1e-10 이내입니다. 대상12207·12408 그룹을 학습에서 제외한 모델을 사용합니다. 노면 정답·실제 상태·원본ZIP·API 키는 포함하지 않습니다.

이 폴더의 `requirements.txt`에 기록한 의존성을 설치한 뒤 `python -X utf8 run_offline.py`를 실행합니다. 추론에 외부 접속·분석/예측 서비스·새 학습이 필요하지 않습니다. Python DNS·주요 소켓 인터페이스를 차단하며 OS 전체 격리 보장은 아닙니다.

온도 범위는 다른 개발 그룹의 지점 균등90% 절대 OOF 오차입니다. 공간 교환가능성이 입증되지 않았고90% 포함률을 보장하지 않습니다. 공식04 결빙 확률·도로 안전 판정으로 해석하지 않습니다. 참가 권한 내 로컬 검토용으로 보존하며 원본 프로젝트의 출처·이용·공개 조건을 함께 확인합니다.
''', encoding='utf-8')
    cals = read(STUDY / 'calibrations.json')['seohaean_seocheon']
    manifest = dict(status='private_weather_memory_review_bundle', built_at_utc=datetime.now(timezone.utc).isoformat(), python=platform.python_version(),
                    station='12207', date_kst=str(date.date()), rows=144, warmup_rows=72, components=old_names+new_names, baseline_components=old_names,
                    history_columns=['asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_dewpoint', 'aws_rain_15m', 'aws_wind_speed'], memory_features=FEATURES,
                    weights=dict(zip(old_names+new_names, [1/6, 1/6, 1/6, 1/4, 1/4])), global_radii={n: cals[n+'_global']['global']['radius'] for n in range_names},
                    input_signatures={str(p.relative_to(ROOT)): sha(p) for p in pinned}, final_submission_model=False, external_prediction_api_required=False,
                    files={p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()})
    write(OUT / 'bundle_manifest.json', manifest)
    result = subprocess.run([sys.executable, '-X', 'utf8', str(OUT / 'run_offline.py')], cwd=OUT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    (OUT / 'replay.log').write_bytes(result.stdout)
    if result.returncode: raise RuntimeError('Preserve failed standalone replay log')
    verification = dict(status='weather_memory_private_bundle_verified', checked_at_utc=datetime.now(timezone.utc).isoformat(), returncode=result.returncode,
                        manifest_sha256=sha(OUT / 'bundle_manifest.json'), replay_log_sha256=sha(OUT / 'replay.log'), source_files=len(manifest['files']),
                        source_bytes=sum((OUT / n).stat().st_size for n in manifest['files']), assessment_outcomes_used=False, submitted=False)
    write(OUT / 'verification.json', verification); print(result.stdout.decode('utf-8')); print(verification)


if __name__ == '__main__': main()
