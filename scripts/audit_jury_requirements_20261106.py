"""공식 요구와 최종 파일·실행 증거를 연결하고 수상 경쟁력의 한계를 따로 기록한다."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys,shutil,re
import pandas as pd,numpy as np,nbformat
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model';D=W/'icy_road_documents'

def main():
    out=W/'requirements_review'
    assert not (out/'receipt.json').exists()
    out.mkdir(exist_ok=True)
    primary=B/'results/evaluation/observations_predictions.csv'
    original=ROOT/'outputs/private/competition_submission/icy_road_model'
    assert sha(primary)==sha(original/'results/evaluation/observations_predictions.csv')
    f=pd.read_csv(primary,dtype={'station_id':str},parse_dates=['prediction_time_kst'],float_precision='round_trip')
    cols={'highway_name','station_name','station_id','prediction_time_kst','observed_surface_state','predicted_ice','observed_road_temperature_c','estimated_road_temperature_c'}
    assert cols<=set(f) and len(f)==103680 and set(f.station_id)=={'12410','33411','23402'}
    assert not f.duplicated(['station_id','prediction_time_kst']).any()
    assert f.prediction_time_kst.dt.tz is None and f.prediction_time_kst.eq(f.prediction_time_kst.dt.floor('10min')).all()
    plan=json.loads((B/'extended_training_plan.json').read_text('utf8'));protected={'12410','33411','23402'}
    assert not set(plan['allowed_stations'])&protected and len(plan['allowed_stations'])==23
    for name in ['training_extended_temperature.parquet','training_weather_temperature.parquet']:
        ids=set(pd.read_parquet(B/'data'/name,columns=['station']).station)
        assert ids==set(plan['allowed_stations']) and not ids&protected
    weather=pd.read_parquet(B/'data/validation_weather.parquet')
    assert len(weather)==103680 and not set(weather)&{'ice','road_temp','observed_ice','state_raw','state','label','target'}
    assert set(weather.station)==protected
    assert {'asos_solar_altitude_deg','asos_solar_sine_positive'}<=set(weather)
    source=json.loads((B/'technical/full_validation_input.json').read_text('utf8'))
    assert source['status']=='full_protected_cli_exact' and source['input_sha256']==sha(B/'data/validation_weather.parquet')
    nb=nbformat.read(B/'notebooks/analysis.ipynb',as_version=4);nbformat.validate(nb)
    assert len([c for c in nb.cells if c.cell_type=='code'])==12
    execution_log=(W/'notebook_execution.log').read_bytes()
    log=execution_log.decode('utf-16' if execution_log.startswith(b'\xff\xfe') else 'utf8')
    assert '12 code cells; outputs not saved' in log
    assert not any(c.outputs for c in nb.cells if c.cell_type=='code')
    assert sha(B/'notebooks/training.ipynb')==sha(original/'notebooks/training.ipynb')
    frozen=json.loads((original/'manifest.json').read_text('utf8'))['files']
    model_hashes={n:sha(B/n) for n in frozen if n.endswith('.joblib')}
    assert all(v==frozen[n]['sha256'] for n,v in model_hashes.items())
    failed=json.loads((ROOT/'outputs/private/unconstrained_icing_selection_20261106/summary.json').read_text('utf8'))
    assert not failed['promote'] and failed['new_model_fits']==0 and not failed['protected_outcomes_used']
    compact={k:failed[k] for k in ['status','decisions','promotion_gates','promote','new_model_fits','threshold_searches','common_valid_pairs','protected_outcomes_used','new_independent_assessment','production_model_changed']}
    compact['metrics']={n:{k:r['1'][k] for k in ['precision','recall','f1']} for n,r in failed['reports'].items()}
    compact['calendar_sensitivity']=failed['sensitivity']
    (B/'technical/threshold_selection_review.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2)+'\n','utf8')
    p=B/'AI_USAGE.md';s=p.read_text('utf8')
    s+='''
재현율 하한을 제거한 내부 F1 선택도 별도로 확인했다. 저장된 지역 이중 제외 모형 점수를 재사용해 16개 문턱 선택을 검토했으며, 새 모델은 학습하지 않았다. 이 절차의 지역 제외 F1은 0.0036으로 고정 물리 기준 0.0294보다 낮았고, 보호 지점의 정답으로 문턱을 다시 고르지 않았다. [선택 검토 근거](technical/threshold_selection_review.json)를 남기고 제출 판정은 유지했다.
'''
    p.write_text(s,'utf8')
    (D/'AI_USAGE.md').write_text(s.replace('results/evaluation/fixed_temperature_rule_review/comparison.csv','data/fixed_temperature_rule_comparison.csv').replace('technical/threshold_selection_review.json','data/threshold_selection_review.json'),'utf8')
    shutil.copyfile(B/'technical/threshold_selection_review.json',D/'data/threshold_selection_review.json')
    qa='https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId='
    rows=[
        ('보호 3지점의 학습 제외',qa+'693','충족','extended_training_plan.json; data/training_*.parquet','허용 23지점을 실제 파일에서 확인'),
        ('두 겨울의 정확한 10분 KST',qa+'693','충족','results/evaluation/observations_predictions.csv','103,680행·중복 0·10분 격자'),
        ('필수 관측·추정 열',qa+'693','충족','results/evaluation/observations_predictions.csv','고속도로·지점·시각·상태관측·결빙예측·온도관측·온도예측'),
        ('Ice·날짜·지점별 지표',qa+'716','충족','src/evaluation.py; notebooks/analysis.ipynb','실제 Ice가 없는 2지점 제외·지표별 유효 날짜 수 명시'),
        ('같은 시각 타 지점 노면상태 입력 금지',qa+'693','충족','data/validation_weather.parquet; src/submission_runtime.py','기상 입력에 정답 열 없음·기상 시각의 strict-before 검사'),
        ('제공 DEM의 정규화 단위',qa+'693','충족','results/sections/terrain/; licenses/','원 제공 DEM을 미터로 쓰지 않고 별도 원본 DSM 이용'),
        ('자체 공간 기준',qa+'716','대체 기준 적용','results/sections/criteria.csv; results/sections/sensitivity/','기존 100점·A/B/C를 모사하지 않고 새 기준의 근거·민감도 명시'),
        ('10년 기후 산정',qa+'716','해당 항목 미사용','report/analysis_report.pdf','두 겨울의 조건 노출을 10년 기후점수로 가장하지 않음'),
        ('기존 취약구간과 비교',qa+'693','충족','results/inventory/agreement/; maps/sections.html','명목 중첩64·±250m가능81·두 겨울 상위25%중첩0을 모두 제시'),
        ('학습·실행 Notebook 및 모델·데이터','https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564','충족','code/; model/; data/; notebooks/','분석12셀 실제 실행·학습3셀은 동일한 기실행 소스 보존'),
        ('전체 검증 입력과 재현','https://aida.kisti.re.kr/competition/main/selectNotice.do?bbsId=BBSMSTR_AAAAAAAAAAAA&nttId=564','충족','data/validation_weather.parquet; code/check_full_validation.py','전체 온도·결빙 예측103,680행 정확 일치'),
        ('실제 테스트와 설명 데모','https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=659','충족','demo/','실제 오프라인 탐색·전 기간 모형 출력'),
        ('AI 지원과 주요 선택 공개','https://aida.kisti.re.kr/competition/main/selectQna.do?bbsId=BBSMSTR_BBBBBBBBBBBB&nttId=618','충족','AI_USAGE.md','AI 지원 범위·미채택 대안·검토·최종 선택 기록'),
        ('결빙 탐지의 실용 성능','https://aida.kisti.re.kr/competition/main/overview.do','한계','results/evaluation/; report/analysis_report.pdf','날짜별 Precision0.0195·F10.0326, 실서비스 검증 없음'),
        ('상대 수상 경쟁력','https://aida.kisti.re.kr/competition/main/overview.do','확정 불가','공개 심사기준·내부 검토','경쟁팀 결과·비공개 심사점수 없음; 가상 점수나 수상확률 산출 안 함')]
    pd.DataFrame(rows,columns=['requirement','official_source','assessment','evidence','test_or_limitation']).to_csv(B/'technical/requirements_traceability.csv',index=False,encoding='utf-8-sig')
    summary=dict(status='requirements_file_and_execution_audit_passed',primary_csv_rows=103680,training_stations=23,
        training_targets_exclude_protected=True,full_validation_weather_has_no_targets=True,
        main_model_hashes_preserved=model_hashes,primary_prediction_values_unchanged=True,
        analysis_notebook_code_cells_executed=12,training_notebook_same_previously_executed_sources=True,
        criteria_table_is_explicit_alternative=True,actual_field_measurements=0,
        award_probability_or_judge_score_calculated=False,competition_submitted=False,
        at_utc=datetime.now(timezone.utc).isoformat())
    (out/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
    review='''# 로드투인사이트 결과물의 심사 관점 검토

규정에 맞는 파일을 갖추는 것과 수상 경쟁력은 별개다. 현재 결과는 온도 추정의 비교 근거와 실행 재현성이 강점이고, 결빙 탐지의 낮은 정밀도와 부족한 현장 검증이 약점이다. 경쟁팀 결과와 비공개 심사점수 없이 수상권을 확정하거나 예상 점수를 계산하지 않았다.

| 공식 항목 | 확인한 강점 | 남은 약점 |
| --- | --- | --- |
| 창의성 20 | 기상 이력·태양위치·주변 관측망, 중복 기상 정보의 구분, 목록 대조와 추가 계측의 연결 | 회귀·거리 가중·공간 연결 자체는 알려진 방법. 새로운 학습 알고리즘이나 현장 효용을 입증한 연구로 과장할 수 없음 |
| 우수성 50 | 학습 제외 3지점 MAE0.978°C, 기본 회귀 대비 공통 쌍14.6% 감소, 전체103,680행 CLI 정확 재현, 실제 Notebook12셀 실행 | 결빙 Precision0.0195·F10.0326. 실제 양성 지점1곳·64시점으로 독립적 일반화 근거가 제한됨 |
| 효과성 30 | 오프라인 지도·모바일 기록·2쪽 계측 계획·전체 모형 실행 영상 | 실제 현장 측정·제설 의사결정·사고 및 비용 감소 효과는 검증하지 않음 |

## 규정·평가 적용

학습 자료23지점에서 평가3지점을 실제 제외했으며, 필수 관측·예측 열과 정확한10분 시각, 무결빙 지점·날짜별 지표 처리를 확인했다. 자체 기준은 공식 Q&A716의 허용 범위에 맞춰 근거와 민감도를 제시했고 기존100점·A/B/C로 가장하지 않았다. 두 겨울을10년 기후점수로 쓰지 않았다. 세부 대조는 icy_road_model/technical/requirements_traceability.csv에 있다.

## 이번 검토로 보완한 핵심

- 전체 검증 기상에 ASOS 좌표의 태양위치를 포함해, 예제뿐 아니라103,680행 전부를 동일 CLI로 재현할 수 있게 했다. 온도·결빙 예측은 기존 제출값과 정확히 같다.
- 공개 목록의 명목 중첩64구간 중 두 겨울 모두 기상 상위25%에 남는 곳이0개라는 불일치를 보고서에 명시했다. 목록과 중첩 가능한81구간은 지도에 유지하고 추가 계측3구간과 구분했다. 이 숫자를 실제 Ice 정확도나 기존 지정 오류율로 해석하지 않았다.
- 공식 요구에 없는 재현율 하한도 검토했다. 저장 점수를 이용한16개 내부 문턱 선택은 지역 전이에서 성능이 악화되어 채택하지 않았다. 보호 지점의 정답으로 문턱을 다시 고르지 않았다.
- 보고서를14쪽으로 정리하고, 현재 안내의22구간·11범위 및 마감 미확인 표기를 수정할 준비를 했다. 원 데이터의 결측은 유지하고 실행 화면에서는 입력 없음·미산출로 설명했다.

## 문장과 화면의 판단

버전 이력·추상적인 홍보 문구·검증하지 않은 운영 성과를 앞세우지 않았다. 도로 위치와 비교 수치, 무엇을 직접 확인해야 하는지 중심으로 구성했다. 시각 검수는 실제 렌더와 화면에 근거하며, 사람이 쓴 것처럼 보인다는 보증이나 AI 판별기 점수로 품질을 대신하지 않았다. AI 지원 내역은 공식 요구대로 공개했다.

## 수상 기대에 대한 판단

온도 추정의 개선과 자료·실행의 완성도는 제출할 만한 근거가 있다. 그러나 결빙 탐지 성능만 놓고 수상권에 충분하다고 판단하기는 어렵다. 특히 낮은 정밀도를 지도·문장으로 보완했다고 성능이 개선된 것은 아니다. 현재의 설득력은 검증된 온도 추정, 정직한 실패 분석, 목록과 추가 계측의 구분, 재현 가능한 전달물에 있다.

근거: [공식 심사 기준](https://aida.kisti.re.kr/competition/main/overview.do), [과제 Q&A716](https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=716), [scikit-learn 문턱 선택](https://scikit-learn.org/stable/modules/classification_threshold.html), [Aurora 지수 프레임워크](https://www.intrans.iastate.edu/wp-content/uploads/2026/03/standardized_framework_road_condition_indices_w_cvr.pdf).
'''
    (W/'JURY_REVIEW.md').write_text(review,'utf8')
    print('규정·실행 대조와 점수를 만들어내지 않은 심사 관점 검토를 기록했습니다.',flush=True)
if __name__=='__main__':main()
