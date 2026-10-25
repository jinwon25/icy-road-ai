"""새 4지역의 입력 검증→고정 모델→예측 봉인→정답 수집→일회 평가를 분리한다."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import warnings
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.blind_icing import FIELDS, normalize_weather, daily_metrics, summarize_days, event_table, paired_bootstrap
from src.anchored_icing import linear_features, anchored_prediction
from src.synoptic_icing import sample_weights
from src.weather_features import prior_join
from src.two_winter import validate
from src.offline_runtime import deny_network
from src.data_source import sha256_file as sha
from src.kma_rwis_download import daily_requests, load_auth_key, parse_observations, exact_ten_minute_grid
from src.kma_rwis_transport import ValidatedRoadClient
from scripts.evaluate_synoptic_icing import read,write
from scripts.evaluate_thermal_classification import available
from scripts.fresh_station_validation import ensure_unopened,old_freezes

PRIVATE=ROOT/'outputs/private'
CONFIG=ROOT/'config/blind_icing_20261025.json'
DEFAULT=PRIVATE/'blind_icing_20261025_v2'


def now(): return datetime.now(timezone.utc).isoformat()


def weather_join(index,weather,mapping):
    parts=[]
    for station,g in index.groupby('station',sort=True):
        s=weather.loc[weather.station.eq(str(mapping[station]))].drop(columns='station')
        parts.append(prior_join(g,s,'asos'))
    return pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)


def weather_quality(weather,winters):
    rows=[]
    for station,g in weather.groupby('station'):
        for a,b in winters:
            f=g.loc[g.source_time.ge(a)&g.source_time.lt(b)].sort_values('source_time')
            expected=int((pd.Timestamp(b)-pd.Timestamp(a))/pd.Timedelta(hours=1))
            r=dict(station=station,winter=int(a[:4]),expected_hours=expected,received_hours=len(f),missing_hours=expected-len(f))
            for _,(name,_,_) in FIELDS.items():r[name+'_coverage']=float(f[name].notna().sum()/expected)
            adjacent=f.source_time.diff().eq(pd.Timedelta(hours=1))
            r['air_jumps_over_10c']=int((adjacent&f.air_temp.diff().abs().gt(10)).sum())
            r['dewpoint_above_air_0_5c']=int((f.dewpoint_obs-f.air_temp).gt(.5).sum())
            rows.append(r)
    return pd.DataFrame(rows)


def prepare(out):
    if out.exists():raise FileExistsError('Preserve prepared run')
    plan=read(CONFIG);ensure_unopened(PRIVATE,plan['new_stations']);frozen=old_freezes()
    out.mkdir(parents=True);shutil.copy2(CONFIG,out/'plan.json')
    data=validate(pd.read_parquet(ROOT/plan['development'])).sort_values(['station','time']).reset_index(drop=True)
    assert len(set(data.station))==23 and not set(data.station)&set(plan['new_stations'])
    mapping=pd.read_csv(ROOT/plan['mapping'],dtype={'station':str,'asos_station':str}).set_index('station').asos_station.to_dict()
    screen=ROOT/plan['screen'];sr=read(screen/'receipt.json');assert sha(screen/'screen.csv')==sr['screen_sha256']
    points=pd.read_csv(screen/'screen.csv',dtype={'station':str,'asos_station':str}).loc[lambda f:f.selected].copy()
    assert set(points.station)==set(plan['new_stations'])
    points.to_csv(out/'points.csv',index=False,encoding='utf-8-sig')
    wx={k:normalize_weather(pd.read_parquet(ROOT/plan[k]/'asos_raw_fields.parquet')) for k in ['training_weather','new_weather']}
    quality=pd.concat([weather_quality(f,plan['winters']).assign(source=k) for k,f in wx.items()],ignore_index=True)
    quality.to_csv(out/'weather_quality.csv',index=False)
    core=[k+'_coverage' for k in ['air_temp','humidity','dewpoint_obs','ground_temp']]
    assert quality[core].ge(.95).all().all(), 'Core weather coverage below fixed requirement'
    assert not quality.dewpoint_above_air_0_5c.any(), 'Review dewpoint consistency before sealing'
    assert not quality.loc[quality.source.eq('new_weather'),'air_jumps_over_10c'].any(), 'Review new-site hourly air jumps before sealing'
    oldbase=PRIVATE/'releases/20261007/outputs/private/point_sources/asos.parquet'
    oldextra=PRIVATE/'synoptic_icing_inputs_20261025_v1/asos_extra_source.parquet'
    old=pd.read_parquet(oldbase).merge(pd.read_parquet(oldextra),on=['station','source_time'],validate='one_to_one')
    compared=wx['training_weather'].merge(old,on=['station','source_time'],suffixes=('_api','_provided'),how='outer',indicator=True)
    compared=compared.loc[compared.station.isin(mapping.values())]
    # 학습 관측 248의 유일한 급상승은 제공본과 일치하고 다음 시간에도 유지된다.
    # 급상승 자체를 오류로 단정해 삭제하지 않는다. 새 도로 정답을 보기 전의 검토이다.
    jump=compared.loc[compared.station.eq('248')&compared.source_time.eq('2025-12-19 11:00')]
    assert int(quality.air_jumps_over_10c.sum())==1 and len(jump)==1
    assert float(jump.air_temp_api.iloc[0])==float(jump.air_temp_provided.iloc[0])==12.2
    parity=[]
    for _,(name,_,_) in FIELDS.items():
        a,b=compared[name+'_api'],compared[name+'_provided'];shared=a.notna()&b.notna();diff=(a-b).abs()
        parity.append(dict(variable=name,api_valid=int(a.notna().sum()),provided_valid=int(b.notna().sum()),shared_valid=int(shared.sum()),
            unequal_shared=int((shared&diff.gt(1e-8)).sum()),missingness_diff=int((a.notna()!=b.notna()).sum()),
            max_absolute_difference=float(diff[shared].max()) if shared.any() else None))
    write(out/'input_parity.json',dict(fields=parity,matched_hours=int(compared._merge.eq('both').sum()),
        api_only_hours=int(compared._merge.eq('left_only').sum()),provided_only_hours=int(compared._merge.eq('right_only').sum()),
        decision='Train and query use the same raw API normalization; sparse values remain missing. No fresh outcomes used.'))
    keep=['station','time','group','winter','ice'];index=data[keep].copy();index['original_available']=available(data).to_numpy()
    train=weather_join(index,wx['training_weather'],mapping)
    train['available']=train.original_available&train.asos_air_temp.notna()
    train.to_parquet(out/'training.parquet',index=False,compression='zstd')
    times=pd.DatetimeIndex(np.concatenate([pd.date_range(a,b,freq='10min',inclusive='left').values for a,b in plan['winters']]))
    index=pd.MultiIndex.from_product([plan['new_stations'],times],names=['station','time']).to_frame(index=False)
    index['winter']=np.where(index.time.dt.month.ge(11),index.time.dt.year,index.time.dt.year-1)
    query=weather_join(index,wx['new_weather'],points.set_index('station').asos_station.to_dict())
    query['available']=query.asos_air_temp.notna();assert not {'ice','road_temp','state_raw'}&set(query)
    query.to_parquet(out/'inputs.parquet',index=False,compression='zstd')
    sourcepaths=[CONFIG,ROOT/plan['development'],ROOT/plan['mapping'],screen/'receipt.json',screen/'screen.csv',
        ROOT/plan['input_audit'],ROOT/plan['official_review'],oldbase,oldextra]
    for k in ['training_weather','new_weather']:
        sourcepaths+=list((ROOT/plan[k]).glob('*.txt'))+[ROOT/plan[k]/'asos_raw_fields.parquet',ROOT/plan[k]/'receipt.json']
    write(out/'input_signatures.json',{p.relative_to(ROOT).as_posix():sha(p) for p in sourcepaths})
    write(out/'input_quality.json',dict(status='passed',at_utc=now(),training_rows=len(train),training_available=int(train.available.sum()),
        query_rows=len(query),query_available=int(query.available.sum()),quality_rows=len(quality),frozen_counts=list(frozen),
        provider_qc_flags_available=False,operational_publication_latency_verified=False,new_road_outcomes_read=False,
        reviewed_training_jump='248 2025-12-19 10:00 2.0C to 11:00 12.2C; provided file agrees, 12:00 13.7C. Retained, not certified error-free.'))
    print('INPUTS',len(train),len(query),'available',int(query.available.sum()),flush=True)


def predict(frame,models):
    q=frame[['station','time','winter','available','asos_air_temp']].copy();x=linear_features(frame)
    q['asos_zero']=np.where(q.available,q.asos_air_temp.le(0),np.nan)
    q['air_minus_half']=np.where(q.available,q.asos_air_temp.le(-.5),np.nan)
    with deny_network() as attempts,threadpool_limits(limits=2):
        for name,model in models.items():
            score=model.predict_proba(x)[:,1];q[name+'_score']=score
            q[name]=np.where(q.available,anchored_prediction(q.asos_air_temp,score,1,'reject_only'),np.nan)
    assert not attempts
    return q


def fit(out):
    plan=read(out/'plan.json');ensure_unopened(PRIVATE,plan['new_stations'])
    if (out/'fit_receipt.json').exists():raise FileExistsError('Preserve fixed models')
    train=pd.read_parquet(out/'training.parquet');query=pd.read_parquet(out/'inputs.parquet')
    mask=train.available&train.ice.isin([0,1]);f=train.loc[mask];x=linear_features(f);weights=sample_weights(f,'day')
    assert len(set(f.station))==23 and not set(f.station)&set(query.station)
    models={'logit_day_anchor1':make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler(),LogisticRegression(**plan['logistic_parameters'])),
            'hgb_day_anchor1':HistGradientBoostingClassifier(**plan['hgb_parameters'])}
    receipts=[]
    for name,model in models.items():
        with warnings.catch_warnings(),deny_network() as attempts,threadpool_limits(limits=2):
            warnings.simplefilter('error',ConvergenceWarning)
            kwargs={'logisticregression__sample_weight':weights} if name.startswith('logit') else {'sample_weight':weights}
            model.fit(x,f.ice.to_numpy(int),**kwargs)
        assert not attempts;joblib.dump(model,out/(name+'.joblib'),compress=3)
        receipts.append(dict(candidate=name,rows=len(f),stations=sorted(f.station.unique()),features=list(x),model_sha256=sha(out/(name+'.joblib'))))
        print('FIT',name,len(f),flush=True)
    q=predict(query,models);q.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    write(out/'fit_receipt.json',dict(status='fixed_models_fit',at_utc=now(),models=receipts,weight_mean=float(weights.mean()),
          weighted_positive_fraction=float(np.average(f.ice,weights=weights)),input_sha256=sha(out/'training.parquet'),
          predictions_sha256=sha(out/'predictions.parquet'),test_rows_used_in_fit_or_preprocessing=0))


def verify(out):
    seal=read(out/'prediction_seal.json')
    for p,digest in seal['files'].items():assert sha(out/p)==digest, p
    for p,digest in read(out/'input_signatures.json').items():assert sha(ROOT/p)==digest,p
    for p,digest in seal['code_signatures'].items():assert sha(ROOT/p)==digest,p
    return seal


def seal(out):
    if (out/'prediction_seal.json').exists():raise FileExistsError('Preserve first seal')
    plan=read(out/'plan.json');ensure_unopened(PRIVATE,plan['new_stations']);assert read(out/'input_quality.json')['status']=='passed'
    # 평가·감사 구현까지 포함한다. 이후 문서는 보완할 수 있지만 지표/후보 코드는 바꾸지 않는다.
    codes=list((ROOT/'src').glob('*.py'))+list((ROOT/'scripts').glob('*.py'))
    write(out/'prediction_seal.json',dict(status='all_predictions_frozen_before_outcome_requests',sealed_at_utc=now(),
        new_outcomes_present_at_seal=False,frozen_counts=list(old_freezes()),
        files={p.name:sha(p) for p in out.iterdir() if p.is_file()},
        code_signatures={p.relative_to(ROOT).as_posix():sha(p) for p in codes}))
    verify(out);print('SEALED',sha(out/'prediction_seal.json'),flush=True)


def transport_plans(plan):
    # 기존 전송기의 개발 전용 필드명을 사용하되, 이 수집물은 학습이 금지된 독립 평가이다.
    blocked=read(ROOT/'config/fresh_station_validation.json')['competition_stations_excluded_from_external_requests']
    for a,b in plan['winters']:
        yield dict(**plan['collection'],development_start_kst=a,development_end_kst=str((pd.Timestamp(b)-pd.Timedelta(days=1)).date()),
            station_groups={'blind_test_never_train':plan['new_stations']},collector_permitted_partition='development_only',
            competition_stations_excluded_from_external_requests=blocked)


def collect(out):
    seal=verify(out);plan=read(out/'plan.json');audit=read(out/'prediction_audit.json')
    assert audit['status']=='passed' and audit['seal_sha256']==sha(out/'prediction_seal.json')
    mp=out/'download_manifest.json'
    if not mp.exists():
        ensure_unopened(PRIVATE,plan['new_stations']);manifest=dict(first_request_utc=now(),records={});write(mp,manifest)
    else:manifest=read(mp)
    assert manifest['first_request_utc']>seal['sealed_at_utc']
    folder=out/'observations';folder.mkdir(exist_ok=True);key=load_auth_key(ROOT/'secret.env');done=0
    for p in transport_plans(plan):
        client=ValidatedRoadClient(p,key,out/'transport')
        for station,start,end in daily_requests(p,p['development_start_kst'],p['development_end_kst'],window_minutes=p['window_minutes']):
            identifier=f'{station}_{start:%Y%m%d%H%M}';path=folder/(identifier+'.parquet');done+=1
            if identifier in manifest['records']:
                assert sha(path)==manifest['records'][identifier]['sha256'];continue
            if path.exists():raise FileExistsError('Unrecorded observation; inspect without resampling')
            body,records=client.fetch(station,start,end);minute=parse_observations(body,station,start,end);f=exact_ten_minute_grid(minute)
            f.to_parquet(path,index=False,compression='zstd')
            manifest['records'][identifier]=dict(station=station,start_kst=start.isoformat(),end_kst=end.isoformat(),
                downloaded_at_utc=now(),sha256=sha(path),rows=len(f),minute_rows=len(minute),transport=records,
                invalid_timestamp_rows_excluded=int(minute.attrs.get('invalid_timestamp_rows_excluded',0)))
            write(mp,manifest)
            if done%20==0:print('COLLECT',done,'/ 960',flush=True)
    assert done==len(manifest['records'])==960
    manifest.update(status='complete',completed_at_utc=now());write(mp,manifest);verify(out);old_freezes()
    print('COLLECTION COMPLETE',flush=True)


def evaluate(out):
    verify(out);plan=read(out/'plan.json');manifest=read(out/'download_manifest.json')
    if (out/'summary.json').exists():raise FileExistsError('One assessment only; audit completed report')
    assert manifest.get('status')=='complete' and len(manifest['records'])==960
    parts=[]
    for key,r in manifest['records'].items():
        path=out/'observations'/(key+'.parquet');assert sha(path)==r['sha256'];parts.append(pd.read_parquet(path))
    observed=pd.concat(parts,ignore_index=True);assert not observed.duplicated(['station','time']).any()
    q=pd.read_parquet(out/'predictions.parquet');f=q.merge(observed[['station','time','ice','state_raw','road_temp','lat','lon']],on=['station','time'],how='left',validate='one_to_one',indicator=True)
    assert len(f)==138240;f=f.sort_values(['station','time']).reset_index(drop=True)
    f.to_parquet(out/'evaluation.parquet',index=False,compression='zstd')
    pop=plan['new_stations'];names=plan['candidate_names'];common=f[names].notna().all(axis=1)
    assert all(np.array_equal(f[n].notna(),common) for n in names)
    coverage=[];points=pd.read_csv(out/'points.csv',dtype={'station':str}).set_index('station')
    for (station,winter),g in f.groupby(['station','winter']):
        good=g.ice.isin([0,1])&g.available
        dx=(g.lat-points.loc[station,'lat']).abs();dy=(g.lon-points.loc[station,'lon']).abs()
        coverage.append(dict(station=station,winter=int(winter),planned_rows=len(g),received_rows=int(g._merge.eq('both').sum()),
            valid_labels=int(g.ice.isin([0,1]).sum()),common_valid=int(good.sum()),common_coverage=float(good.mean()),ice_rows=int((good&g.ice.eq(1)).sum()),
            max_lat_difference=float(dx.max()) if dx.notna().any() else None,max_lon_difference=float(dy.max()) if dy.notna().any() else None))
    write(out/'coverage.json',coverage);reports={};days={};all_days=[]
    for name in names:
        reports[name]={}
        for slots in plan['sensitivity_min_slots']:
            d=daily_metrics(f,f[name],pop,plan['winters'],slots);r=summarize_days(d,pop);reports[name][str(slots)]=r
            if slots==144:
                days[name]=d
                for a,b in plan['winters']:
                    reports[name][a[:4]]=summarize_days(d.loc[d.date_kst.ge(a)&d.date_kst.lt(b)],pop)
            all_days.append(d.assign(candidate=name,min_slots=slots))
        r,e=event_table(f,f[name],f.asos_zero);reports[name]['events']=r;e.to_csv(out/(name+'_events.csv'),index=False)
    pd.concat(all_days,ignore_index=True).to_csv(out/'daily_metrics.csv',index=False)
    primary=plan['primary_candidate'];b=reports['asos_zero']['144'];c=reports[primary]['144']
    evidence=plan['evidence_minimum'];coverage_df=pd.DataFrame(coverage)
    gates=dict(valid_sites=int(coverage_df.groupby('station').common_valid.sum().gt(0).sum())>=evidence['valid_sites'],
        coverage=bool(coverage_df.common_coverage.ge(evidence['coverage_per_site_winter']).all()),
        positive_sites=int(coverage_df.groupby('station').ice_rows.sum().gt(0).sum())>=evidence['positive_sites'],
        positive_events=reports[primary]['events']['observed_events']>=evidence['positive_events'],
        coordinate_consistency=all(r['max_lat_difference'] is not None and r['max_lat_difference']<=.01 and r['max_lon_difference']<=.01 for r in coverage),
        f1_improves=c['f1_fixed_population']>=1.01*b['f1_fixed_population'] and c['f1_fixed_population']>b['f1_fixed_population'],
        each_winter=all(reports[primary][a[:4]]['f1_fixed_population']>=reports['asos_zero'][a[:4]]['f1_fixed_population'] for a,_ in plan['winters']),
        each_site=all(c['station_f1_fixed'][s]>=b['station_f1_fixed'][s] for s in pop),
        no_lost_events=reports[primary]['events']['lost_events']==0)
    for m in ['precision','recall']:
        key=m+'_available_station_mean';gates[m+'_noninferior']=b[key] is not None and c[key] is not None and c[key]>=b[key]
    uncertainty={n:paired_bootstrap(days['asos_zero'],days[n],pop) for n in names if n!='asos_zero'}
    summary=dict(status='one_time_four_site_assessment_complete',evaluated_at_utc=now(),primary_candidate=primary,reports=reports,
        primary_gates=gates,primary_success=all(gates.values()),uncertainty=uncertainty,retuning_permitted=False,
        production_model_changed=False,official_competition_score=False,new_region_same_two_winters=True,
        observed_rows=len(observed),planned_rows=len(f),evaluation_sha256=sha(out/'evaluation.parquet'),
        seal_sha256=sha(out/'prediction_seal.json'),manifest_sha256=sha(out/'download_manifest.json'),frozen_counts=list(old_freezes()))
    write(out/'summary.json',summary);print('EVALUATED',primary,'success',summary['primary_success'],flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=['prepare','fit','seal','collect','evaluate'])
    parser.add_argument('--output',type=Path,default=DEFAULT);args=parser.parse_args();out=args.output.resolve()
    if not out.is_relative_to(PRIVATE.resolve()):raise ValueError('Private output required')
    globals()[args.phase](out)


if __name__=='__main__':main()
