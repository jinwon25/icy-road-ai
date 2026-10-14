"""연구용 내보내기·기준표·지도·한국어 매뉴얼을 통합한다. 공식 제출은 하지 않는다."""
from pathlib import Path
import json
import shutil
import sys
import geopandas as gpd
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write
from src.data_source import sha256_file as sha

OUT=ROOT/'outputs/private/submission_candidate_20261013_v1'

EXPORT='''"""공통 기상 그룹의10분 예측을 위치별 연구CSV로 펼친다. 공식 스키마 미확정."""
from pathlib import Path
import argparse
import pandas as pd
HERE=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--kind',choices=['protected','segment'],required=True)
parser.add_argument('--scale',type=int,choices=[500,1000],default=500)
parser.add_argument('--id');parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
if args.output.exists():raise FileExistsError('Existing export preserved')
index=pd.read_csv(HERE/'data/point_prediction_index.csv',dtype={'id':str,'winter':str,'prediction_group':str})
index=index.loc[index.kind.eq(args.kind)]
if args.kind=='segment':index=index.loc[index.scale_m.eq(args.scale)]
if args.id:index=index.loc[index.id.eq(args.id)]
if index.empty:raise ValueError('Requested location is absent')
args.output.mkdir(parents=True)
for sid,rows in index.groupby('id'):
 parts=[]
 for row in rows.itertuples():
  f=pd.read_parquet(HERE/'data/prediction_groups'/(row.prediction_group+'.parquet'));f['station']=sid;f['winter']=row.winter;parts.append(f)
 result=pd.concat(parts,ignore_index=True).sort_values('time');assert not result.duplicated(['station','time']).any()
 result.to_csv(args.output/(sid+'.csv.gz'),index=False,encoding='utf-8-sig',compression='gzip',na_rep='')
print('연구CSV 내보내기 완료',index.id.nunique())
'''


def main():
    if (OUT/'materials_receipt.json').exists():raise FileExistsError('Preserve materials')
    spatial=read(OUT/'spatial_receipt.json');policy=read(ROOT/'outputs/private/thermal_consensus_20261013_v1/summary.json')
    assert read(ROOT/'outputs/private/thermal_consensus_20261013_v1/independent_verification.json')['summary_sha256']==sha(ROOT/'outputs/private/thermal_consensus_20261013_v1/summary.json')
    (OUT/'code/export_predictions.py').write_text(EXPORT,encoding='utf-8')
    criteria=[
        dict(condition_evidence='insufficient_input',definition='유효ASOS 또는 수분3열이 모두 없는 경우',predicted_ice='null',interpretation='입력 보완과 현장 확인 필요',validated_accident_probability=False),
        dict(condition_evidence='cold_wet_consensus',definition='평균온도<=0, 수분조건, 두 성분 모두<=0',predicted_ice='1',interpretation='모델 합의가 있는 저온·수분 조건. 현장 확인 대상',validated_accident_probability=False),
        dict(condition_evidence='cold_wet_disagreement',definition='평균온도<=0, 수분조건, 한 성분은>0',predicted_ice='1',interpretation='성분 간 불일치가 있는 경계 조건. 센서 확인 대상',validated_accident_probability=False),
        dict(condition_evidence='criterion_not_met',definition='유효입력에서 저온·수분 결합 기준을 만족하지 않음',predicted_ice='0',interpretation='해당 모델 기준 미충족. 안전이나 결빙 부재의 보장 아님',validated_accident_probability=False)]
    pd.DataFrame(criteria).to_csv(OUT/'data/condition_evidence_criteria.csv',index=False,encoding='utf-8-sig')
    cols={'seg_id':'seg_id','route_nm':'route_nm','len_m':'len_m','cold_wet_fraction':'cw_frac','cold_wet_hours':'cw_hours',
        'temperature_valid_slots':'t_valid','ice_valid_slots':'i_valid','consensus_slots':'cons_slot','disagreement_slots':'dis_slot',
        'bridge_code_fraction':'bridge_fr','tunnel_code_fraction':'tunnel_fr','asos_distance_km':'asos_km','aws_distance_km_max':'aws_km'}
    write(OUT/'figures/shapefile_column_dictionary.json',cols)
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
    boundary=gpd.read_file(ROOT/'outputs/private/segment_exposure_20261009_v1/boundary.gpkg')
    for scale in [500,1000]:
        fig,axes=plt.subplots(1,2,figsize=(10.8,7.2),constrained_layout=True)
        for ax,winter in zip(axes,['2024','2025']):
            g=gpd.read_file(OUT/'figures'/f'candidate_conditions_{scale}m_{winter}.gpkg')
            shp=g[list(cols)+['geometry']].rename(columns=cols);shp.to_file(OUT/'figures'/f'candidate_conditions_{scale}m_{winter}.shp',encoding='UTF-8')
            reread=gpd.read_file(OUT/'figures'/f'candidate_conditions_{scale}m_{winter}.shp');assert len(reread)==len(g) and reread.crs==g.crs
            boundary.to_crs(g.crs).plot(ax=ax,color='#f3f5f7',edgecolor='#b4c0ca',linewidth=.45)
            g.plot(ax=ax,column='cold_wet_fraction',cmap='viridis',vmin=0,vmax=1,linewidth=2.2)
            ax.set_title(f'{winter}-{int(winter)+1} 겨울\n{len(g):,}개 구간, 중점 추정',fontweight='bold');ax.set_axis_off()
        fig.suptitle(f'전북 고속도로 {scale}m 추정 저온·수분 조건 노출',fontsize=16,fontweight='bold')
        bar=fig.colorbar(plt.cm.ScalarMappable(norm=Normalize(0,1),cmap='viridis'),ax=axes,shrink=.64,pad=.025)
        bar.set_label('유효 추정 시점 중 저온·수분 조건 비율')
        fig.text(.03,.008,'기상 기반 후보 추정. 실제 Ice·사고 확률·공식 위험등급의 검증값이 아닙니다. 공식 이정·시설 범위 미확정.',fontsize=9)
        fig.savefig(OUT/'figures'/f'candidate_condition_map_{scale}m.jpg',dpi=190,bbox_inches='tight');plt.close(fig)
    reference=[
        dict(title='공식 문제',url='https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do',application='두 겨울·보호3곳·10분 예측·공간 산출물·재현 코드 요구사항'),
        dict(title='공식 Q&A633',url='https://aida.kisti.re.kr/competition/problem/PROB_000000000004604/detail/commuDetail.do?bbsId=BBSMSTR_000000000319&nttId=633',application='미탐일Precision 제외, Recall/F1=0 포함'),
        dict(title='Bouilloud et al. 2009',url='https://journals.ametsoc.org/view/journals/apme/48/12/2009jamc1900.1.xml',application='온도·수분·눈의 물리적 연관을 참고. 해당 논문의 수치모델을 구현하거나 성능을 전용하지 않음'),
        dict(title='Cawley and Talbot 2010',url='https://jmlr.org/papers/v11/cawley10a.html',application='반복 개발 선택 편향과 독립 평가 한계를 명시'),
        dict(title='Roberts et al. 2017',url='https://doi.org/10.1111/ecog.02881',application='공간 그룹 제외 검증. 적절한 공간차단 수준은 과제별 조건 필요'),
        dict(title='scikit-learn 1.6 threshold tuning',url='https://scikit-learn.org/1.6/modules/classification_threshold.html',application='결정 기준 선택을 학습·외부 그룹과 분리. 이번에는 고정 물리 가설을 자체 지표로 비교')]
    write(OUT/'reports/reference_applications.json',reference)
    pd.DataFrame([dict(policy=n,f1=r['report']['daily']['144']['f1_available_station_mean'],precision=r['report']['daily']['144']['precision_available_station_mean'],
        recall=r['report']['daily']['144']['recall_available_station_mean'],fp=r['report']['fp'],fn=r['report']['fn'],lost_events=r['retention']['lost_events'],eligible=r['eligible']) for n,r in policy['reports'].items()]).to_csv(OUT/'reports/thermal_policy_comparison.csv',index=False,encoding='utf-8-sig')
    for relative in ['summary.json','independent_verification.json','decisions.json']:
        shutil.copy2(ROOT/'outputs/private/thermal_consensus_20261013_v1'/relative,OUT/'validation'/('thermal_'+relative))
    for relative in ['README.md','AI_USAGE.md','requirements.txt','requirements-dev.txt']:
        shutil.copy2(ROOT/relative,OUT/'code'/('project_'+relative))
    for folder in ['src','scripts','config','tests','notebooks','docs','.github']:
        shutil.copytree(ROOT/folder,OUT/'code/project'/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'),dirs_exist_ok=True)
    for relative in ['README.md','AI_USAGE.md','requirements.txt','requirements-dev.txt']:
        shutil.copy2(ROOT/relative,OUT/'code/project'/relative)
    text='''# 전북 고속도로 결빙 분석 제출 후보

첫 겨울 허용23곳으로 학습한 고정 기상12 입력의 MSE/MAE300 모델 평균과 저온·수분 판정을 실행합니다. 모델·재현 학습 표·보호3곳 두 겨울10분 추정·500m/1km 공간파일·조건 기준표를 포함합니다. 이 묶음은 비공개 제출 후보이며 공식 제출이나 독립 성능 통과를 뜻하지 않습니다.

## 성능과 선택 판단

기존 공간 제외 개발9곳에서 온도MAE1.200531°C, 일별 지점 평균F1 0.030633, Precision0.052803, Recall0.774688입니다. Recall은 양성 관측이 있는8곳의 평균이며9곳 전체 평균은 미정의입니다.144유효슬롯 조건은 잠정입니다. 기존 온도3종 평균보다FP/FN은 감소했으나 일평균Precision은 낮습니다. 이번18개 열·수분 가설의 공간 중첩 선택은 모두 기존 기준을 유지했고, 개선 수치가 있던 조합도 기존 사건을 놓쳐 채택하지 않았습니다.

모든23곳으로 새 적합한2모델은 실행용 대표 후보입니다. 전체 적합 모델의 재대입 점수를 일반화 성능으로 계산하지 않았습니다. 새 보호 예측을 과거 보호 정답으로 다시 채점하거나 튜닝하지 않았습니다. 둘째 겨울은 공공 기상 입력만 사용했고 학습 정답은 사용하지 않았습니다.

## 빠른 실행

Python3.11과CPU 환경입니다. GPU·외부 예측API·인증키는 필요하지 않습니다. 의존성 설치 이후의 추론은 로컬파일만 읽습니다.

```powershell
python -m pip install -r requirements.txt
python -X utf8 code/predict.py --input data/weather_example.csv --output validation/new_example.csv
python -X utf8 code/train.py --output validation/new_models
python -X utf8 code/export_predictions.py --kind protected --output validation/target_csv
python -X utf8 code/export_predictions.py --kind segment --scale 500 --id 8eabed369e9c40e7 --output validation/segment_csv
```

기존 출력 경로가 있으면 중단합니다. 의존성 설치와 추론 실행은 구분합니다. 원본GIS·공공기상 캐시의 전체 재구축은 원본 프로젝트 환경이 필요합니다. 이 묶음의 `code/train.py`와 기상 그룹 예측은 포함된 자료로 재현할 수 있습니다. `code/project/`는 실제 개발에 사용한 전체 코드·설정·검사·노트북·문서이며 이전 실험의 모든 원자료·모델까지 포함한 것은 아닙니다.

## 입력과 결측

`station,time`과 기상12열, `rain15_max_3h,asos_snow_cm`을 받습니다. 시간은Asia/Seoul의정확한10분 시각입니다. ASOS/AWS는60분 이내의 엄격한 이전 관측입니다. 평균에 필요한12입력의순서와 버전은 `training_plan.json`에 있습니다. 공개기상 결합 규약은 `code/project/src/segment_exposure.py`·`weather_features.py`에 있습니다.

정답열 `road_temp,ice,state_raw,label`은 추론 입력에서 거부합니다. 미래·중복·비정규 시각도 거부합니다. 공식 숫자 결측값을NaN으로 정리하고, 오래된AWS 입력은 제거합니다. 유효ASOS가 없거나 수분3열이 모두 없으면 판정은null입니다. 현재 후보에는 기존 분류의fallback 모델을 포함하지 않았으므로 입력 부족 시 예측 거부가 기존 개발 판정과 다른 동작입니다. 이 차이를 숨기지 않고18개 보호 시점의결측을 기록했습니다.

## 결과 파일

| 위치 | 내용 |
| --- | --- |
| `data/protected_predictions_10min.csv.gz` | 보호3곳·두 겨울103,680행. 유효추정103,662행·입력 부족18행. 정답·공식 점수 없음 |
| `data/point_prediction_index.csv` | 위치·겨울·규모와공통기상 예측그룹 대응2,538행 |
| `data/prediction_groups/` | 138그룹·2,384,640행의공통10분 예측. 위치별CSV는내보내기명령으로생성 |
| `data/weather_groups/` | 위 예측의실제공공기상 입력. 노면온도·상태 정답 없음 |
| `data/segment_candidate_summary.csv` | 500m843개·1km423개의두 겨울 중점추정·환경코드·분모 |
| `data/condition_evidence_criteria.csv` | 입력부족·저온수분합의·성분불일치·기준미충족의해석 |
| `figures/` | GPKG·Shapefile 부속파일·열 사전·두 겨울JPG 지도 |
| `reports/` | 분석·매뉴얼PDF·고정가설비교·일차문헌적용근거 |
| `model/` | 저장2모델과학습영수증 |
| `validation/` | 시간결합·추론·재적합·위치대응 검산과실제CLI로그 |

## 적용 범위

모델 성분의 차이는 전체 예측오차나90%보장 범위가 아닙니다. 지도 색은저온·수분조건의추정시점 비율입니다. 실제 Ice확률·사고확률·공식A/B/C 위험등급은 검증하지 않았습니다. 기준미충족0도 안전을 뜻하지 않습니다. 교량·터널코드 비율은 정적도로원자료의속성이며 실제시설길이·현재운영상태·결빙영향을 입증하지 않습니다.

새1km지도도 구간중점 추정입니다. 이전1km의500m 길이 가중통계와다르므로 두 결과의차이를 모델개선량으로사용하지 않습니다. 공식이정·정확한시설범위·센서/제설이력·미사용지점의성능 재현은남아 있습니다. 최종CSV열·결측표기·결과물제출 날짜·일부일평균정책은 공식공지확인후맞춰야 합니다.

원본ZIP·신청서·자필서명·개인정보·API키·Git이력·보호정답·이미개봉한평가정답은 포함하지 않았습니다. 제공자료와파생물은참가권한내에서비공개로취급합니다. 데이터가제외된공개용저장소와구별합니다.
'''
    (OUT/'README.md').write_text(text,encoding='utf-8')
    write(OUT/'materials_receipt.json',dict(status='candidate_maps_criteria_manual_complete',geo_files=4,shapefile_sets=4,map_images=2,
        development_policies_not_promoted=True,official_schema=False,submitted=False))


if __name__=='__main__':main()
