"""현재 후보 ZIP의 포함 자료만 사용하는 출력 없는 심사용 노트북을 생성한다."""
import argparse
from pathlib import Path
import nbformat


def notebook():
    md, code = nbformat.v4.new_markdown_cell, nbformat.v4.new_code_cell
    cells = [md('''# 현재 결빙 후보: 학습 범위와 오프라인 추론 검토

이 노트북은 제출 후보를 압축 해제한 폴더의 포함 자료만 사용합니다. 원래 연구 폴더의 `outputs/private/`, 원본 ZIP, 인증키는 필요하지 않습니다. Python 3.11에서 `python -m pip install -r requirements-notebook.txt`로 노트북 실행 의존성을 설치하고 같은 환경의 Jupyter 커널을 선택합니다.

기상 12변수 기반 MSE·MAE 두 모델의 고정 평균을 유지합니다. 아래 예제는 **학습 범위 내 하루의 실행 검증**이며 새 지점 성능이 아닙니다. 개발 지표도 반복 사용한 첫 겨울 자료의 진단이며 공식 점수가 아닙니다. 보호 관측소 12410·33411·23402의 정답은 읽지 않습니다.

셀을 위에서부터 실행합니다. 기본 실행은 재학습 없이 학습 자료의 범위, 저장 모델 추론, 기존 개발 지표를 확인합니다. 선택적 학습 셀은 별도 폴더에서 같은 설정을 재현합니다. 출력은 노트북 파일에 저장하지 않습니다.'''),
    code('''from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd
import joblib
from IPython.display import display

ROOT = next((p for p in [Path.cwd().resolve(), *Path.cwd().resolve().parents]
             if (p / 'training_plan.json').is_file() and (p / 'model/model_card.json').is_file()), None)
if ROOT is None:
    raise FileNotFoundError('제출 후보 ZIP을 압축 해제한 폴더의 notebooks/에서 실행하세요.')
sys.path.insert(0, str(ROOT))
from src.submission_runtime import FEATURES, infer
from src.submission_io import read_weather
from src.offline_runtime import deny_network
from src.validation import PROTECTED_STATIONS, assert_training_stations
from src.method_blending import ALLOWED, domain
from src.qa633_metrics import daily_table, aggregate

plan = json.loads((ROOT / 'training_plan.json').read_text('utf-8'))
card = json.loads((ROOT / 'model/model_card.json').read_text('utf-8'))
assert not card['performance_qualified']
print('후보 준비 상태: 성능 적합 판정 보류 / 공식 점수 아님')'''),
    md('''## 학습 자료와 전처리 범위

첫 겨울의 허용 23곳으로 적합한 모델입니다. 다음 겨울 및 보호 관측소가 학습에 포함되지 않았는지 행 식별자와 적합 영수증을 확인합니다. 입력은 관측소 정답을 포함하지 않는 기상 12변수이며, 기상 시각은 목표 시각보다 엄격히 이전입니다. 결측 대체는 저장된 HGB 모델과 추론 코드의 기존 규약을 사용합니다.'''),
    code('''training_keys = pd.read_parquet(ROOT / 'data/training_weather_temperature.parquet', columns=['station', 'time'])
domain(training_keys)
assert_training_stations(training_keys.station)
assert set(training_keys.station) == set(plan['allowed_stations']) == set(ALLOWED)
assert list(FEATURES) == plan['features']
fits = json.loads((ROOT / 'model/fit_receipts.json').read_text('utf-8'))
for fit in fits:
    assert fit['training_rows'] == len(training_keys)
    assert set(fit['training_stations']) == set(ALLOWED)
    assert fit['features'] == list(FEATURES)
print({'training_rows': len(training_keys), 'stations': training_keys.station.nunique(),
       'first_time': str(training_keys.time.min()), 'last_time': str(training_keys.time.max()),
       'protected_overlap': sorted(set(training_keys.station) & PROTECTED_STATIONS)})'''),
    md('''## 저장 모델의 실제 추론

CSV를 무손실 부동소수점 파서로 읽습니다. 저장 모델 두 개만 불러와 144개 10분 시각을 추론하고, 포함된 기존 기대 결과와 전 열을 정확히 비교합니다. 기상 입력이 부족하면 판정은 null이며 비결빙 0으로 바꾸지 않습니다.'''),
    code('''with deny_network() as inference_attempts:
    weather = read_weather(ROOT / 'data/weather_example.csv')
    models = [joblib.load(ROOT / 'model' / (name + '.joblib'))
              for name in ['weather12_mse300', 'weather12_mae300']]
    prediction = infer(weather, models)
    expected = read_weather(ROOT / 'data/example_predictions.csv')
    expected.time = pd.to_datetime(expected.time)
    pd.testing.assert_frame_equal(prediction, expected, check_dtype=False, check_exact=True)
assert not inference_attempts
print({'rows': len(prediction), 'identical_to_expected': True, 'network_attempts': 0})
display(prediction.head(3))'''),
    md('''## 기존 개발 지표 검산

저장된 공간 제외 예측을 재집계합니다. 날짜별 Precision·Recall·F1을 각각 계산한 뒤 지점별 날짜 평균, 지점 균등 평균을 구합니다. 미탐만 있는 날의 Precision은 제외하고 Recall·F1은 0, 양쪽 무결빙은 제외합니다. 부분 날짜 허용 기준 144·130·72·1은 잠정 민감도이며 그중 좋은 점수를 골라 모델을 바꾸지 않습니다.

전체 행 온도 MAE 1.200531°C와 지점 균등 MAE 1.200440°C를 구별합니다. 현재 일별 F1 0.030633은 단순 ASOS 기온 기준선 0.071122보다 낮습니다. 지표별 날짜·지점 분모 및 FP/FN도 함께 읽어야 합니다.'''),
    code('''with deny_network() as metric_attempts:
    base = ROOT / 'research/baselines'
    benchmark = json.loads((base / 'summary.json').read_text('utf-8'))
    fixed = pd.read_parquet(base / 'fixed_comparator_predictions.parquet')
    domain(fixed)
    rows = []
    checked_reports = 0
    for method, previous in benchmark['reports'].items():
        for minimum in [144, 130, 72, 1]:
            days = daily_table(fixed, fixed[method], benchmark['population'], minimum)
            actual, stations = aggregate(days, benchmark['population'])
            for key, value in actual.items():
                saved = previous['coverage'][str(minimum)][key]
                if isinstance(value, float):
                    assert np.isclose(value, saved, atol=1e-12, rtol=0), (method, minimum, key)
                else:
                    assert value == saved, (method, minimum, key)
            checked_reports += 1
            if minimum == 144:
                rows.append({'method': method, 'daily_f1': actual['f1_available_station_mean'],
                             'f1_days': actual['f1_days'], 'f1_stations': actual['f1_stations'],
                             'FP': previous['counts']['fp'], 'FN': previous['counts']['fn']})
assert not metric_attempts and checked_reports == 24
display(pd.DataFrame(rows))
print('기존 개발 지표 24개 재현 완료 / 새 학습·공식 평가 없음')'''),
    md('''## 선택적 고정 설정 재학습

기본값은 `False`입니다. 재현이 필요할 때만 `RUN_REFIT=True`로 변경합니다. 첫 겨울 허용 자료로 같은 두 모델을 새로운 임시 폴더에 적합하며 기존 저장 모델을 덮어쓰지 않습니다. 파라미터 탐색·임계값 변경·보호 정답 평가는 하지 않습니다. 기존 재학습 검산 기록도 `validation/independent_verification.json`에 포함돼 있습니다.'''),
    code('''RUN_REFIT = False
if RUN_REFIT:
    import subprocess
    import tempfile
    output_parent = Path(tempfile.mkdtemp(prefix='icy_road_fixed_refit_'))
    subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'code/train.py'),
                    '--output', str(output_parent / 'models')], cwd=ROOT, check=True)
    print('같은 설정 재학습 완료:', output_parent / 'models')
else:
    print('저장 모델 검토 완료. 재학습은 실행하지 않았습니다.')'''),
    md('''## 제출 전에 남은 확인

- 최신 결과물 마감 날짜·접수 방식, 최종 CSV 열·행키·파일명·결측 표현은 운영진 안내 확인이 필요합니다. 11월 6일은 참가신청 종료일입니다.
- 2026년 10월 19일 데모영상 Q&A의 답변 본문을 아직 확인하지 못했습니다. 현재 영상은 `demo/inference_demo.webm`이며 새 형식·길이 제한 충족은 미확인입니다.
- 보호 예측의 입력 부족 18행은 그대로 null입니다. 원 기상 근거 없이 채우지 않습니다.
- [현재 보고서](../reports/current/current_report.pdf), [AI 활용 기록](../AI_USAGE.md), [실행 데모](../demo/index.html)를 함께 검토합니다. 이 노트북은 제출 및 외부 공개를 수행하지 않습니다.''')]
    return nbformat.v4.new_notebook(cells=cells, metadata={
        'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
        'language_info': {'name': 'python', 'version': '3.11'}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    value = notebook()
    nbformat.validate(value)
    with args.output.open('x', encoding='utf-8') as f:
        nbformat.write(value, f)
    print('제출용 노트북 생성:', args.output)


if __name__ == '__main__':
    main()
