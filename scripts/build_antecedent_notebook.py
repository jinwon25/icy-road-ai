"""누적 기상 입력 연구의 학습·재추론·선택 결과를 읽는 노트북을 생성한다."""
from pathlib import Path
import nbformat as nb

ROOT=Path(__file__).resolve().parents[1]


def main():
    path=ROOT/'notebooks/antecedent_forcing_review_20261031.ipynb'
    if path.exists():raise FileExistsError('Preserve existing notebook')
    cells=[nb.v4.new_markdown_cell('''# 누적 기상 조건의 추가 가치

2026년 Yi & Seo의 도로 결빙 연구에서 제안한 누적 냉각·수증기 조건을 미관측 도로의 기상 대리변수에 적용합니다.
원 논문의 노면온도 입력·Snow/Ice 포함 정답·미래 사건 예측을 그대로 재현하는 실험은 아닙니다.
대회에 맞춰 Ice 단독 10분 상태를 유지하고, 실제 도로 노면온도나 상태 이력을 입력에 넣지 않습니다.

원본 작업 공간의 완료 결과와 검산 기록이 필요합니다. 위에서 아래로 실행하며 외부 API를 호출하지 않습니다.
기존 9개 개발 지점의 반복 비교이므로 새 독립 평가나 공식 대회 성적으로 해석하지 않습니다.
전체 계획과 구현은 `config/antecedent_forcing_20261031.json`, `scripts/evaluate_antecedent_forcing.py`에 있습니다.'''),
    nb.v4.new_code_cell('''from pathlib import Path
import json, sys
import numpy as np
import pandas as pd
import torch
from IPython.display import display
ROOT=next(p for p in [Path.cwd(),*Path.cwd().parents] if (p/'src/antecedent_forcing.py').exists())
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.antecedent_forcing import fit_forcing, correction_from_features
from src.offline_runtime import deny_network
read=lambda path: json.loads(path.read_text(encoding='utf8'))
study=ROOT/'outputs/private/antecedent_forcing_20261031_v2'
settings=read(study/'plan.json')['settings']
summary=read(study/'summary.json');audit=read(study/'independent_verification.json')
assert audit['status']=='passed' and audit['summary_sha256']==sha(study/'summary.json')
assert not audit['protected_outcomes_read'] and not audit['new_four_site_outcomes_read']
torch.set_num_threads(2);torch.use_deterministic_algorithms(True)
print('새 적합',len(summary['fits']),'기존 대조 재사용',len(summary['reused']))'''),
    nb.v4.new_markdown_cell('''## 자료와 기상 이력

40개 순간 변수와 64개 이력 포함 변수를 같은 학습 조건으로 비교합니다. AWS는 목표보다 이전이면서
15분 이내인 관측만 사용하고, 30분·6시간 시간상수로 누적값을 계산합니다. 지점·겨울 경계에서 초기화하며
긴 공백에는 누적 상태를 감쇠만 합니다. ASOS 시간 자료의 반복 연결을 독립적인 10분 관측으로 세지 않습니다.
ERA5-Land 변수는 사후 재분석으로 실시간 운영 성능을 주장할 수 없습니다.

특성 행은 학습 정답을 제외하기 전에 시간순으로 계산합니다. 정답이나 노면온도는 특성 파일에 포함되지 않습니다.'''),
    nb.v4.new_code_cell('''source=pd.read_parquet(ROOT/settings['source']).sort_values(['station','time']).reset_index(drop=True)
receipt=read(study/'feature_receipt.json')
assert sha(study/'features.parquet')==receipt['sha256']
features=pd.read_parquet(study/'features.parquet')
assert len(features)==len(source) and not set(source.station)&set(settings['blocked_stations'])
assert not set(['ice','road_temp','station'])&set(features)
display(pd.Series({'자료 행':len(source),'허용 지점':source.station.nunique(),'순간 변수':len(receipt['instantaneous_columns']),'전체 변수':len(features.columns)}))
display(features[['asos_air_temp','asos_air_cold_30m','asos_air_cold_360m','asos_ground_deposition_30m']].head(12))'''),
    nb.v4.new_markdown_cell('''## 학습과 저장 모델의 재추론

한 지역 전체를 제외한 누적 입력 모델을 읽어 해당 지역의 저장 예측과 정확히 대조합니다.
중앙값과 표준화는 학습 지역에서만 적합합니다. BCE 손실·학습 횟수·정규화·최대 ±2°C 보정은 대조군과 같습니다.
`RUN_REFIT=True`로 바꾸면 같은 학습을 다시 수행하고 모든 저장 배열과 비교합니다.
전체 20모델 및 기존 대조 10모델 검산은 `scripts/audit_antecedent_forcing.py`에서 수행합니다.'''),
    nb.v4.new_code_cell('''record=next(r for r in summary['fits'] if r['kind']=='dose' and len(r['excluded'])==1)
held=source.group.isin(record['excluded']);query=source.loc[held]
train=source.loc[~held&source.available&source.ice.isin([0,1])]
assert not set(train.station)&set(query.station)
assert sha(study/record['model'])==record['sha256']
with np.load(study/record['model'],allow_pickle=False) as archive:model=dict(archive)
RUN_REFIT=False
with deny_network() as attempts:
    if RUN_REFIT:
        repeat=fit_forcing(train,features.loc[train.index,record['features']],settings)
        for name in model:np.testing.assert_array_equal(repeat[name],model[name])
    correction=correction_from_features(features.loc[query.index,record['features']],model)
assert not attempts
scores=pd.read_parquet(study/('__'.join(record['excluded'])+'__scores.parquet'))
np.testing.assert_array_equal(correction,scores.dose)
print('저장 예측과 일치:',len(correction),'행, 제외 지역:',record['excluded'])'''),
    nb.v4.new_markdown_cell('''## 지역 내부 선택과 최종 비교

주 결과는 내부 지역의 일별 F1로 선택한 `mean_f1`입니다. 순간 입력 대조는 누적 입력 후보를 제외한 같은 선택 절차입니다.
외부 지역의 점수를 보고 주 후보를 바꾸지 않습니다. 144개 시각이 완전하고 해당 지표 분모가 양수인 날짜를 사용합니다.
지표별 유효 날짜가 달라질 수 있어 기준선 날짜 고정 F1과 기존 탐지 사건 손실도 함께 확인합니다.'''),
    nb.v4.new_code_cell('''names=['asos_zero','matched_instantaneous','mean_f1','recall_guard']
rows=[]
for name in names:
    report=summary['reports'][name]
    rows.append({'후보':name,'F1':report['all']['f1_fixed_population'],
        'Precision':report['all']['precision_available_station_mean'],'Recall':report['all']['recall_available_station_mean'],
        '기준선 날짜 고정 F1':report['baseline_calendar_f1'],**report['events']})
display(pd.DataFrame(rows))
display(pd.DataFrame([{'제외 지역':d['held'],**d['selected']} for d in summary['decisions']]))
display(pd.Series(summary['gates'],name='사전 채택 조건'))
print('주 후보 채택 조건 통과:',summary['primary_success'])'''),
    nb.v4.new_markdown_cell('''## 두 겨울 비교와 판단 범위

한겨울의 이득이 다른 겨울의 손실을 가리는지 확인합니다. 7일 블록 재표집은 이미 만든 개발 예측의 날짜 구성 민감도입니다.
새 지역에 대한 신뢰구간으로 해석하지 않습니다. 공식 보호 3곳과 이미 개봉한 별도 4곳의 정답은 이 연구에 읽지 않았습니다.
논문 출처·변경한 조건·실패 기록·최종 판단은 `docs/research/ANTECEDENT_FORCING_20261031.md`에 남깁니다.'''),
    nb.v4.new_code_cell('''import matplotlib.pyplot as plt
season=pd.DataFrame({name:{year:summary['reports'][name]['winters'][year]['f1_fixed_population'] for year in ['2024','2025']} for name in names})
display(season)
ax=season.plot.bar(figsize=(9,4),rot=0)
ax.set_xlabel('Winter start year');ax.set_ylabel('Mean daily F1');ax.set_ylim(bottom=0)
plt.tight_layout();plt.show()
display(pd.DataFrame(summary['sensitivity']).T)''')]
    notebook=nb.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
        'language_info':{'name':'python','version':'3.11.2'}})
    nb.validate(notebook);nb.write(notebook,path);print(path)


if __name__=='__main__':main()
