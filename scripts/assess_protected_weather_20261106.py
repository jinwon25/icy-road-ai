"""봉인된 지정 지점 기상 예측을 고정 관측소 기준과 대조한다. 학습·선택 없음."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys,zipfile
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import competition_archive,sha256_file as sha
from src.observation_io import daily_members
from src.road_weather_transfer import allowed_csv,clean_target,regression_numbers
from src.offline_runtime import deny_network
from scripts.seal_protected_weather_20261106 import W,B,STATIONS,write

OUT=W/'protected_weather'
EST={'air_temperature':'estimated_air_temperature_c','relative_humidity':'estimated_humidity_pct','wind_speed':'estimated_wind_speed_ms'}

def validate_seal():
    seal=json.loads((OUT/'prediction_seal.json').read_text('utf8'))
    for name,digest in seal['files'].items():assert sha(OUT/name)==digest,name
    for name,digest in seal['input_signatures'].items():assert sha(ROOT/name)==digest,name
    return sha(OUT/'prediction_seal.json')

def resampling(frame,target,methods,rng):
    # 세 지점에 같은 날짜를 적용하고 각 겨울 안에서 연속 7일을 순환 재표본화한다.
    days=[pd.date_range(f'{y}-11-01',f'{y+1}-03-01',inclusive='left',freq='D') for y in [2024,2025]]
    good=np.isfinite(frame[target])
    for col in methods.values():good &=np.isfinite(frame[col])
    z=frame.loc[good].copy();z['date']=z.time.dt.normalize()
    if not set(z.station)==set(STATIONS):
        return [dict(target=target,baseline=m,status='not_estimable_missing_site_observations',
            common_pairs=len(z),replicates=0,block_days=7) for m in methods if m!='estimated']
    arrays={}
    for method,col in methods.items():
        z['ae']=abs(z[col]-z[target])
        a=z.groupby(['station','date']).ae.agg(['sum','count'])
        arrays[method]=[np.array([[a.loc[(s,d),'sum'] if (s,d) in a.index else 0 for d in dates] for s in STATIONS]) for dates in days]
    counts=[np.array([[a.loc[(s,d),'count'] if (s,d) in a.index else 0 for d in dates] for s in STATIONS]) for dates in days]
    deltas={m:[] for m in methods if m!='estimated'}
    for _ in range(2000):
        index=[((rng.integers(0,len(d),size=int(np.ceil(len(d)/7)))[:,None]+np.arange(7))%len(d)).ravel()[:len(d)] for d in days]
        denominator=sum(c[:,ix].sum(axis=1) for c,ix in zip(counts,index))
        mae={m:np.mean(sum(a[:,ix].sum(axis=1) for a,ix in zip(groups,index))/denominator) for m,groups in arrays.items()}
        for m in deltas:deltas[m].append(mae['estimated']-mae[m])
    result=[]
    for method,values in deltas.items():
        values=np.asarray(values);lo,hi=np.quantile(values,[.025,.975])
        result.append(dict(target=target,baseline=method,delta_mae_percentile_2_5=float(lo),delta_mae_percentile_97_5=float(hi),
            bootstrap_fraction_delta_below_zero=float((values<0).mean()),replicates=len(values),block_days=7,
            interpretation='고정 3지점·두 겨울의 날짜 의존성 민감도; 새 도로 모집단의 신뢰구간이나 승률 아님'))
    return result

def evaluate(frame,target,methods):
    common=np.isfinite(frame[target])
    for col in methods.values():common &=np.isfinite(frame[col])
    rows=[]
    for scope,q in [('all',frame),*[(str(y),v) for y,v in frame.groupby('winter')]]:
        for station,z in [('pooled',q),*list(q.groupby('station'))]:
            good=common.loc[z.index];z=z.loc[good]
            for method,col in methods.items():
                rows.append(dict(target=target,period=scope,station=station,method=method,**regression_numbers(z[target],z[col])))
        for method in methods:
            site=[r for r in rows if r['target']==target and r['period']==scope and r['station'] in STATIONS and r['method']==method]
            assert len(site)==3
            complete=all(r['n']>0 for r in site)
            rows.append(dict(target=target,period=scope,station='station_macro',method=method,n=sum(r['n'] for r in site),
                available_stations=sum(r['n']>0 for r in site),
                **{k:float(np.mean([r[k] for r in site])) if complete else None for k in ['mae','bias','rmse']}))
    return rows

def main():
    assert not (OUT/'assessment.json').exists()
    seal=validate_seal();plan=json.loads((OUT/'plan.json').read_text('utf8'))
    archive_path=competition_archive(ROOT/'outputs/private/releases/20261007')
    if not (OUT/'outcome_access.json').exists():
        write(OUT/'outcome_access.json',dict(opened_utc=datetime.now(timezone.utc).isoformat(),prediction_seal_sha256=seal,
            archive_sha256=sha(archive_path),reader_sha256=sha(Path(__file__)),weather_columns_only=True))
    else:
        previous=json.loads((OUT/'outcome_access.json').read_text('utf8'));assert previous['prediction_seal_sha256']==seal
        write(OUT/'missing_target_handling_addendum.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),
            original_reader_sha256=previous['reader_sha256'],reader_sha256=sha(Path(__file__)),
            reason='The first run stopped before metric export because missing target observations invalidated the planned complete-site macro. Report NA and zero available-site denominators; do not fill or substitute targets.',
            predictions_unchanged=True,training=False,threshold_selection=False))
    columns=['관측 지점번호','관측시각 (KST)','기온 (C)','습도 (%)','1분 풍속 (m/s)']
    parts=[];members=[]
    with zipfile.ZipFile(archive_path) as archive:
        for i,member in enumerate(daily_members(archive,'RWIS')):
            frame,skipped=allowed_csv(archive,member,STATIONS,columns)
            frame.columns=['station','time',*EST];frame.station=frame.station.str.strip();frame.time=pd.to_datetime(frame.time,errors='raise')
            parts.append(frame);members.append(dict(member=member,rows=len(frame),crc=archive.getinfo(member).CRC))
            if (i+1)%80==0:print('Fixed weather assessment CSV',i+1,flush=True)
    raw=pd.concat(parts,ignore_index=True);assert not raw.duplicated(['station','time']).any()
    assert set(raw.station)==set(STATIONS)
    for target in EST:raw[target]=clean_target(raw[target],plan['target_bounds'][target])
    predicted=pd.read_parquet(OUT/'predictions.parquet')
    f=predicted.merge(raw,on=['station','time'],how='left',validate='one_to_one',indicator=True)
    assert f._merge.eq('both').sum()==len(raw)
    f['winter']=np.where(f.time.dt.month>=7,f.time.dt.year,f.time.dt.year-1)
    f['observation_row_present']=f._merge.eq('both');f=f.drop(columns='_merge')
    metrics=[];uncertainty=[];rng=np.random.default_rng(61106)
    for target,col in EST.items():
        methods={'asos_reference':'asos_'+target,'aws_reference':'aws_'+target,'estimated':col}
        metrics.extend(evaluate(f,target,methods));uncertainty.extend(resampling(f,target,methods,rng))
    f.to_parquet(OUT/'observations_predictions.parquet',index=False,compression='zstd')
    f.to_csv(OUT/'observations_predictions.csv.gz',index=False,encoding='utf-8-sig',compression='gzip')
    pd.DataFrame(metrics).to_csv(OUT/'metrics.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(uncertainty).to_csv(OUT/'paired_day_block_sensitivity.csv',index=False,encoding='utf-8-sig')
    # 기존 제출 노면온도와 직접 기온 관측소 기준의 추가 대조. 값을 이용한 보정·선택은 하지 않는다.
    surface_path=B/'results/evaluation/observations_predictions.csv'
    surface=pd.read_csv(surface_path,dtype={'station_id':str},parse_dates=['prediction_time_kst'],float_precision='round_trip')
    surface=surface.rename(columns={'station_id':'station','prediction_time_kst':'time'})
    surface=surface.merge(predicted[['station','time','asos_air_temperature','aws_air_temperature']],on=['station','time'],validate='one_to_one')
    surface['winter']=np.where(surface.time.dt.month>=7,surface.time.dt.year,surface.time.dt.year-1)
    surface_metrics=evaluate(surface,'observed_road_temperature_c',{'asos_air_reference':'asos_air_temperature','aws_air_reference':'aws_air_temperature','estimated':'estimated_road_temperature_c'})
    pd.DataFrame(surface_metrics).to_csv(OUT/'surface_temperature_benchmarks.csv',index=False,encoding='utf-8-sig')
    availability=f.groupby(['station','winter'])[[*EST]].count().reset_index()
    availability.to_csv(OUT/'target_availability.csv',index=False,encoding='utf-8-sig')
    summary=dict(status='fixed_protected_weather_audited_no_training',seal_sha256=seal,rows=len(f),observed_raw_rows=len(raw),
        missing_observation_calendar_rows=int((~f.observation_row_present).sum()),metrics=[r for r in metrics if r['period']=='all' and r['station']=='station_macro'],
        paired_block_sensitivity=uncertainty,surface_temperature_benchmarks=[r for r in surface_metrics if r['period']=='all' and r['station']=='station_macro'],
        no_new_model_fitting=True,no_threshold_selection=True,other_protected_state_and_surface_temperature_previously_opened=True,
        surface_evaluation_input_sha256=sha(surface_path),members=members)
    assert validate_seal()==seal
    write(OUT/'assessment.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k in ['status','rows','metrics','surface_temperature_benchmarks']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    with deny_network():main()
