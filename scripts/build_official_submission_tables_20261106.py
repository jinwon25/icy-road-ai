"""모형·프로필 봉인 후 Q&A693의 필수 관측 대조 CSV와 고정 예측의 공식 방식 지표를 생성한다.

보호 관측값은 이 제출·평가 전용 프로세스에서만 읽으며 학습·선택 함수로 전달하지 않는다.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,re,sys,zipfile
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha
from scripts.evaluate_objective_icing import verify_preserved
from src.observation_io import daily_members,read_columns,numeric_observations
from src.validation import canonical_station_id,normalize_state,regression_metrics
from src.official_metrics_20261106 import evaluate

P=ROOT/'outputs/private';OUT=P/'official_submission_tables_20261106_v14'
SEAL=P/'final_selection_20261106_v14/selection_seal.json'
TARGETS={'12410':('서해안고속도로','부곡교'),'33411':('통영-대전중부고속도로','삼봉'),'23402':('호남고속도로','해전')}

def main():
    if OUT.exists():raise FileExistsError('Preserve fixed final assessment')
    seal=read(SEAL);assert seal['status']=='final_selection_frozen_before_observation_delivery_join'
    for name,digest in seal['source_signatures'].items():assert sha(ROOT/name)==digest,name
    frozen=verify_preserved();outcome_access_started=datetime.now(timezone.utc).isoformat()
    archive=ROOT/'DATA AI 경진대회 데이터(20261007).zip'
    expected=read(ROOT/'config/data_source.json')['corrected_release']['sha256']
    assert sha(archive)==expected
    source=P/'submission_candidate_20261101_v12'
    primary=source/'research/latest/competition_profile_review_20261101_v1/protected_score_priority_predictions.csv.gz'
    load=lambda p:pd.read_csv(p,dtype={'station':str,'predicted_ice':'Int64'},parse_dates=['time'],float_precision='round_trip')
    pred=load(primary);old=load(source/'exports/protected_predictions_10min.csv')
    assert len(pred)==103680 and set(pred.station)==set(TARGETS) and not pred.duplicated(['station','time']).any()
    pd.testing.assert_frame_equal(pred[['station','time','estimated_road_temp_c']],old[['station','time','estimated_road_temp_c']],check_exact=True)
    assert pred.predicted_ice.isna().equals(old.predicted_ice.isna()) and pred.predicted_ice.isna().sum()==18
    observations=[];source_members=[]
    with zipfile.ZipFile(archive) as z:
        for member in daily_members(z,'RWIS'):
            f=read_columns(z,member,['관측시각 (KST)','관측 지점번호','고속도로','관측 지점명','노면상태','노면온도 (광학)'],
                ['time','station','provided_highway','provided_station_name','observed_surface_state','observed_road_temperature_raw'])
            f['station']=f.station.map(canonical_station_id);f=f.loc[f.station.isin(TARGETS)].copy()
            f['time']=pd.to_datetime(f.time,errors='raise')
            day=pd.to_datetime(re.search(r'_(\d{8})\.csv$',member).group(1),format='%Y%m%d')
            f=f.loc[f.time.dt.normalize().eq(day)].copy()
            f['observed_ice']=pd.array(f.observed_surface_state.map(normalize_state),dtype='Int64')
            f['observed_road_temperature_c']=numeric_observations(f.observed_road_temperature_raw)
            observations.append(f);source_members.append(member)
    obs=pd.concat(observations,ignore_index=True)
    assert not obs.duplicated(['station','time']).any() and set(obs.station)==set(TARGETS)
    merged=pred.merge(obs,on=['station','time'],how='left',validate='one_to_one',indicator=True)
    missing_observation_rows=int(merged['_merge'].ne('both').sum())
    # 원본의 관측 공백도 계획 시각과 예측을 유지하며 NA로 표기한다. 비결빙으로 채우지 않는다.
    merged['highway_name']=merged.station.map(lambda s:TARGETS[s][0]);merged['station_name']=merged.station.map(lambda s:TARGETS[s][1])
    merged['prediction_time_kst']=merged.time.dt.strftime('%Y-%m-%d %H:%M:%S')
    merged['station_id']=merged.station;merged['estimated_road_temperature_c']=merged.estimated_road_temp_c
    merged['predicted_ice_preserved_v2']=old.predicted_ice.to_numpy()
    columns=['highway_name','station_name','station_id','prediction_time_kst','observed_surface_state','observed_ice',
        'predicted_ice','observed_road_temperature_c','estimated_road_temperature_c','predicted_ice_preserved_v2',
        'icing_policy','temperature_status','moisture_status','provided_highway','provided_station_name']
    OUT.mkdir()
    table=merged[columns].copy();table.to_csv(OUT/'protected_observed_predictions_10min.csv',index=False,encoding='utf-8-sig')
    table.to_parquet(OUT/'protected_observed_predictions_10min.parquet',index=False,compression='zstd')
    reloaded=pd.read_csv(OUT/'protected_observed_predictions_10min.csv',dtype={'station_id':str,'predicted_ice':'Int64','observed_ice':'Int64'},float_precision='round_trip')
    pd.testing.assert_series_equal(reloaded.estimated_road_temperature_c,table.estimated_road_temperature_c,check_exact=True)
    pd.testing.assert_series_equal(reloaded.predicted_ice,table.predicted_ice,check_exact=True)
    metric_frame=merged[['station','time','observed_ice']].rename(columns={'observed_ice':'ice'})
    reports={};days=[];stations=[]
    for name,values in [('score_priority_asos_zero',merged.predicted_ice),('preserved_v2',old.predicted_ice)]:
        reports[name]={}
        for minimum in [1,144]:
            s,t,d=evaluate(metric_frame,values,minimum_valid_slots=minimum,station_population=sorted(TARGETS))
            s['scope']='frozen_final_predictions_after_selection; not official server score'
            reports[name][str(minimum)]=s
            days.append(d.assign(profile=name,minimum_valid_slots=minimum));stations.append(t.assign(profile=name,minimum_valid_slots=minimum))
    pd.concat(days,ignore_index=True).to_csv(OUT/'protected_daily_metrics.csv',index=False,encoding='utf-8-sig')
    pd.concat(stations,ignore_index=True).to_csv(OUT/'protected_station_metrics.csv',index=False,encoding='utf-8-sig')
    regression=[]
    for station,q in merged.groupby('station'):
        regression.append(dict(station=station,scope='whole_two_winters',**regression_metrics(q.observed_road_temperature_c,q.estimated_road_temperature_c)))
    regression.append(dict(station='pooled',scope='whole_two_winters',**regression_metrics(merged.observed_road_temperature_c,merged.estimated_road_temperature_c)))
    pd.DataFrame(regression).to_csv(OUT/'protected_temperature_metrics.csv',index=False,encoding='utf-8-sig')
    codebook=[('highway_name','고속도로명','문자열'),('station_name','관측지점명','문자열'),('station_id','관측소 번호','정규화한 ID'),
        ('prediction_time_kst','관측·예측 대조 시각','KST 10분; 시간 허용오차 없음'),('observed_surface_state','제공된 노면상태 원 코드','결측·미정의 코드는 observed_ice에서 NA'),
        ('observed_ice','유효 Ice 관측','1=Ice, 0=유효 비결빙, NA=결측·미정의'),('predicted_ice','기본 제출 프로필의 결빙 판단','1/0/NA; 기온<=0 기준선'),
        ('observed_road_temperature_c','제공 광학 노면온도 관측','°C; 결측코드는 NA'),('estimated_road_temperature_c','AI v3 추정 노면온도','°C'),
        ('predicted_ice_preserved_v2','보존된 이전 v2의 판단','비교용 1/0/NA')]
    pd.DataFrame(codebook,columns=['column','meaning_ko','unit_and_missing']).to_csv(OUT/'column_dictionary.csv',index=False,encoding='utf-8-sig')
    (OUT/'README.md').write_text('''# 공식 Q&A693 관측·예측 대조표

`protected_observed_predictions_10min.csv`는 보호 3지점·두 겨울·10분 단위 103,680행의 제출 대조표입니다. 고속도로명·지점명·시각·관측 노면상태·예측 결빙·관측 노면온도·AI 추정 노면온도를 포함합니다. `column_dictionary.csv`에서 열·단위·결측 의미를 확인합니다.

모형·분류 프로필을 선택·봉인한 뒤 별도 제출·평가 프로세스에서 원본 관측을 결합했습니다. 이 관측값을 새 모형 학습·선택·입력으로 사용하지 않았습니다. 추론 입력과 이 관측 대조표는 별도 파일입니다. 비교표를 추론 입력으로 전달하지 않습니다.

기본 프로필은 AI 노면온도 v3와 별도 F1 우선 ASOS 0°C 분류 기준선입니다. 기존 v2도 비교 열·지표로 보존합니다. 분류의 단순 기준선을 새로 학습한 AI 분류기의 개선이라고 주장하지 않습니다. 입력 부족 18개 판단은 NA로 유지합니다.

`protected_daily_metrics.csv`와 `protected_station_metrics.csv`는 Q&A556·633·693·716의 날짜→지점 집계와 무결빙 지점 제외를 적용합니다. 부분 날짜 최소 관측량은 미명시이므로 최소1과144를 모두 제공합니다. 지표별 날짜·지점 수, 산출불가 사유를 함께 기재합니다. 이 로컬 고정 평가를 공식 서버 성적이라고 부르지 않습니다.

온도 BIAS는 예측−관측이며 MAE·RMSE는 같은 유효 쌍입니다. 선택 봉인과 원본·예측·결합 결과의 해시는 receipt.json을 따릅니다. 제공 데이터의 이용·보안·폐기 조건을 유지합니다.
''',encoding='utf8')
    assert verify_preserved()==frozen
    signatures={p.name:sha(p) for p in OUT.iterdir() if p.is_file()}
    write(OUT/'receipt.json',dict(status='fixed_submission_observation_tables_verified',at_utc=datetime.now(timezone.utc).isoformat(),
        outcome_access_started_at_utc=outcome_access_started,selection_frozen_at_utc=seal['at_utc'],selection_seal_sha256=sha(SEAL),
        rows=len(table),stations=3,na_prediction_rows=18,missing_observation_rows=missing_observation_rows,source_archive_sha256=expected,source_member_count=len(source_members),
        code_signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),ROOT/'src/official_metrics_20261106.py']},
        primary_predictions_sha256=sha(primary),original_temperature_predictions_exact=True,observations_used_for_training_or_selection=False,
        protected_outcomes_read_for_final_submission_only=True,reports=reports,regression=regression,files=signatures,preservation=frozen))
    print('FINAL TABLES VERIFIED',len(table),'rows; selection was frozen before observed targets were joined',flush=True)
    print(json.dumps(dict(primary=reports['score_priority_asos_zero']['1'],regression=regression),ensure_ascii=False),flush=True)

if __name__=='__main__':main()