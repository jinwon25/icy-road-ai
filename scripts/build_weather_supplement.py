"""사전 기준·독립 검산을 통과한 기상 목표만 별도 실행 가능한 묶음으로 학습한다."""
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import sys

import nbformat as nbf
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.road_weather_transfer import baselines
from src.road_weather_runtime import INPUT_COLUMNS,predict_weather
from src.offline_runtime import deny_network
from scripts.evaluate_objective_icing import read,write,verify_preserved
from scripts.retrain_weather_supplement import train


def main():
    study=ROOT/'outputs/private/road_weather_transfer_20261031_v1';summary=read(study/'summary.json')
    audit=read(study/'independent_verification.json');plan=read(study/'plan.json')['settings']
    assert audit['status']=='passed' and audit['summary_sha256']==sha(study/'summary.json')
    controls=ROOT/'outputs/private/weather_calibration_controls_20261031_v1'
    control_summary=read(controls/'summary.json');control_audit=read(controls/'independent_verification.json')
    assert control_audit['status']=='passed' and control_audit['summary_sha256']==sha(controls/'summary.json')
    selected=control_summary['selected_targets'];assert selected
    out=ROOT/'outputs/private/weather_observation_supplement_20261031_v1'
    if out.exists():raise FileExistsError('Preserve weather supplement')
    frozen=verify_preserved();out.mkdir(parents=True)
    for folder in ['data','src','scripts','validation','figures','notebooks']:(out/folder).mkdir()
    source=ROOT/plan['input_output']/'development.parquet'
    assert sha(source)==read(source.parent/'receipt.json')['data_sha256']
    f=pd.read_parquet(source)
    valid=np.zeros(len(f),bool)
    for target in selected:
        a,b=baselines(f,target);valid|=f[target].notna().to_numpy()&np.isfinite(a)&np.isfinite(b)
    f=f.loc[valid,['station','time','group','winter']+INPUT_COLUMNS+selected].reset_index(drop=True)
    f.to_parquet(out/'data/training.parquet',index=False,compression='zstd')
    settings=dict(selected_targets=selected,model=plan['model'],allowed_stations=plan['competition_stations']+plan['development_stations'],
        blocked_stations=plan['blocked_stations'],data_sha256=sha(out/'data/training.parquet'),
        source_data_sha256=sha(source),development_summary_sha256=sha(study/'summary.json'),
        development_audit_sha256=sha(study/'independent_verification.json'),
        calibration_controls_sha256=sha(controls/'summary.json'),
        scope='Repeated four-region two-winter development. No independent or official-target weather accuracy claim.')
    write(out/'settings.json',settings)
    source_files=['src/data_source.py','src/observation_io.py','src/road_weather_transfer.py','src/road_weather_runtime.py',
        'src/offline_runtime.py','scripts/predict_weather_supplement.py','scripts/retrain_weather_supplement.py']
    for name in source_files:shutil.copy2(ROOT/name,out/name)
    (out/'src/__init__.py').write_text('',encoding='utf-8')
    packages=['numpy','pandas','scipy','scikit-learn','joblib','pyarrow','threadpoolctl','python-dateutil','pytz','tzdata','six','nbformat','ipykernel','jupyter-client']
    (out/'requirements.txt').write_text('\n'.join(p+'=='+version(p) for p in packages)+'\n',encoding='utf-8')
    metadata=train(out,out/'model')
    # 각 검증 지역·겨울의 앞 18행씩 총 144행. 전체 적합 모형의 실행 예시이며 검증 성능이 아니다.
    example=f.loc[f.group.ne('competition')].groupby(['group','winter'],sort=True).head(18)
    example=example[['station','time']+INPUT_COLUMNS].reset_index(drop=True)
    example.to_csv(out/'data/inference_example.csv',index=False,encoding='utf-8-sig')
    csv=pd.read_csv(out/'data/inference_example.csv',dtype={'station':str})
    with deny_network() as attempts:prediction=predict_weather(csv,out/'model')
    assert not attempts and len(prediction)==144
    prediction.to_csv(out/'data/expected_predictions.csv',index=False,encoding='utf-8-sig')
    for name in ['summary.json','independent_verification.json','coverage.csv']:
        shutil.copy2(study/name,out/'validation'/name)
    for name in ['summary.json','independent_verification.json','training_constants.csv']:
        shutil.copy2(controls/name,out/'validation'/('calibration_'+name))
    review=ROOT/'outputs/private/road_weather_review_20261031_v1'
    for name in ['observation_estimation_metrics.csv','mae_comparison.png']:
        shutil.copy2(review/name,out/('figures' if name.endswith('.png') else 'validation')/name)
    shutil.copy2(ROOT/'docs/research/ROAD_WEATHER_TRANSFER_20261031.md',out/'RESEARCH.md')
    lines=['# 도로 기상 관측값 추정 보완 모형','',
        '기존 노면온도·결빙 모델을 유지하면서 미관측 지점의 기상값을 추정하는 별도 실행 묶음입니다. 반복 사용한 개발 4지역을 각각 두 겨울 학습에서 제외한 결과로 판단했으며 신규 독립·공식 제외 지점의 성능이 아닙니다.','',
        '| 추정 대상 | AWS 우선 기준선 MAE | 잔차 모형 MAE | 개선율 |','| --- | ---: | ---: | ---: |']
    for target in selected:
        metrics=summary['reports'][target]['metrics'];a=metrics['aws_fallback']['pooled']['mae'];b=metrics['residual_hgb']['pooled']['mae']
        lines.append(f'| {target} | {a:.6f} | {b:.6f} | {(1-b/a)*100:.2f}% |')
    lines+=['','기온 단위는 °C, 습도 오차는 %p, 풍속은 m/s입니다. 전체 MAE 감소가 모든 지역·모든 지표의 개선을 뜻하지 않습니다. 상세 지역·겨울 수치와 실패한 후보도 `validation/observation_estimation_metrics.csv`에 있습니다. 기상값 추정 개선을 결빙 F1 개선으로 대신하지 않습니다.','',
        '## 환경과 실행','',
        '검증 환경은 Windows, Python 3.11.2, CPU입니다. GPU·외부 AI 서비스·API 인증정보가 필요하지 않습니다. 새 가상환경에서 이 폴더를 작업 디렉터리로 사용합니다. 라이브러리 버전은 `requirements.txt`에 고정했습니다.','',
        '```powershell','python -m venv .venv','.venv/Scripts/python.exe -m pip install -r requirements.txt',
        '.venv/Scripts/python.exe scripts/predict_weather_supplement.py --model model --input data/inference_example.csv --output prediction.csv',
        '.venv/Scripts/python.exe scripts/retrain_weather_supplement.py --bundle . --output model_retrained','```','',
        '출력 파일·학습 폴더가 이미 있으면 덮어쓰지 않습니다. `data/expected_predictions.csv`는 144행의 재현 확인용이며 학습 자료의 일부에 대한 전체 적합 모형의 추론입니다. 이 값으로 검증 정확도를 계산하면 안 됩니다.','',
        '## 구성과 입력','',
        '`data/training.parquet`은 허용된 지점의 기상 학습 입력·목표이고 `model/`은 전체 허용 학습 자료로 적합한 채택 모형입니다. `src/`와 `scripts/`에 전처리·가중치·학습·추론 코드가 있으며 `validation/`은 지역 제외 연구와 검산입니다. 기존 보호 지점과 개봉 완료 독립 4곳의 새 정답을 포함하지 않습니다.','',
        '입력 CSV는 예시와 같은 28개 기상 열을 요구합니다. ASOS 시간차는 0분 초과 60분 이하, AWS는 0분 초과 15분 이하의 과거 관측이어야 합니다. 시간차가 유효하지 않으면 해당 출처를 결측으로 취급하고 ASOS가 유효하지 않은 행에는 예측을 제공하지 않습니다. 입력 생성은 관측 시각을 기준으로 하며 실제 서비스 제공 지연까지 검증한 실시간 예보가 아닙니다.','',
        '이 모형의 출력은 지역 기상 추정값이며 노면온도·현장 결빙 여부·사고확률이 아닙니다. 습도는 0–100%, 풍속은 0 이상으로 제한합니다. 목표 기상·노면 정답·지점 ID·연도·사후 ERA5를 특성에 넣지 않습니다.','',
        '## 자료·AI 활용','',
        '대회 제공 2026-10-07 수정 배포본과 기상청에서 기존에 확보한 개발용 도로기상 자료·ASOS·AWS를 이용했습니다. 대회 자료의 공개·재배포 허용을 가정하지 않으며 이 묶음은 비공개 심사·로컬 검토용입니다. 외부 참고 논문과 적용 차이는 `RESEARCH.md`에 있습니다. 생성형 AI(Codex)를 분석 설계·코드 작성·실험·검산·문서 작성에 활용했습니다. 자동 수행·검증한 내용을 참가자가 직접 수동 검증했다고 표시하지 않습니다. 본체 프로젝트의 `AI_USAGE.md`에 의사결정과 실패 대안을 기록합니다.','']
    (out/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    nb=nbf.v4.new_notebook();nb.metadata.kernelspec=dict(display_name='Python 3',language='python',name='python3')
    nb.cells=[
        nbf.v4.new_markdown_cell('# 기상 관측값 추정 보완 모형\n\n이 폴더의 데이터·모형만으로 추론을 확인합니다. 기온·습도·풍속 중 개발 기준을 통과한 목표만 포함합니다. 예시 144행은 전체 적합 모형의 재현 확인용입니다. 성능은 지역 전체를 제외한 `validation/observation_estimation_metrics.csv`를 사용합니다.'),
        nbf.v4.new_code_cell("from pathlib import Path\nimport sys,json\nimport pandas as pd\nimport numpy as np\nBUNDLE = Path.cwd() if (Path.cwd()/'settings.json').is_file() else Path.cwd().parent\nsys.path.insert(0,str(BUNDLE))\nfrom src.data_source import sha256_file\nfrom src.road_weather_runtime import predict_weather\nfrom src.offline_runtime import deny_network\nsettings=json.loads((BUNDLE/'settings.json').read_text('utf-8'))\nassert sha256_file(BUNDLE/'data/training.parquet')==settings['data_sha256']\ndata=pd.read_parquet(BUNDLE/'data/training.parquet')\nprint('학습 행 수:',len(data),'지점 수:',data.station.nunique())\nmetrics=pd.read_csv(BUNDLE/'validation/observation_estimation_metrics.csv')\nmetrics.loc[metrics.scope.eq('all') & metrics.target.isin(settings['selected_targets'])]"),
        nbf.v4.new_code_cell("example=pd.read_csv(BUNDLE/'data/inference_example.csv',dtype={'station':str})\nwith deny_network() as attempts:\n    result=predict_weather(example,BUNDLE/'model')\nassert not attempts\nexpected=pd.read_csv(BUNDLE/'data/expected_predictions.csv',dtype={'station':str})\npd.testing.assert_frame_equal(result,expected,check_exact=False,rtol=1e-14,atol=1e-12)\nprint('재현 일치:',len(result),'행')\nresult.head()"),
        nbf.v4.new_markdown_cell('## 선택 실행: 처음부터 학습\n\n`RUN_REFIT=True`이면 포함 학습 자료와 고정 설정으로 전체 모형을 새 임시 폴더에 적합하고 예시 추론을 대조합니다. 완료 후 임시 모형은 정리합니다. 원 제출 모형은 변경하지 않습니다. 학습에는 지점·겨울의 역빈도 가중치가 적용됩니다.'),
        nbf.v4.new_code_cell("RUN_REFIT=False\nif RUN_REFIT:\n    import tempfile\n    from scripts.retrain_weather_supplement import train\n    with tempfile.TemporaryDirectory(prefix='weather_refit_') as temporary:\n        new_model=Path(temporary)/'model'\n        train(BUNDLE,new_model)\n        with deny_network() as attempts:\n            replay=predict_weather(example,new_model)\n        assert not attempts\n        pd.testing.assert_frame_equal(result,replay,check_exact=True)\n    print('전체 재학습·144행 추론 일치')\nelse:\n    print('기본 추론 검증 완료. 전체 재학습은 RUN_REFIT=True로 실행합니다.')")]
    nbf.write(nb,out/'notebooks/weather_observation_supplement.ipynb')
    with (out/'README.md').open('a',encoding='utf-8') as stream:
        stream.write('\n`notebooks/weather_observation_supplement.ipynb`에서 학습 자료·제외 지역 지표·144행 추론을 확인하고 선택적으로 전체 재학습을 실행할 수 있습니다. nbformat·ipykernel·jupyter-client 버전도 고정했으며 Jupyter 또는 VS Code Notebook에서 이 가상환경을 선택합니다.\n')
    assert verify_preserved()==frozen
    write(out/'receipt.json',dict(status='weather_supplement_built',selected_targets=selected,training_rows=len(f),
        training_stations=sorted(f.station.unique()),example_rows=len(prediction),metadata=metadata,
        source_summary_sha256=sha(study/'summary.json'),preservation=frozen,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print('SUPPLEMENT BUILT',selected,flush=True)


if __name__=='__main__':main()
