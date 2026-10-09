"""주변 노면 입력 없이 첫 겨울 온도를 예측하는 그룹 제외 회귀 비교."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shutil,sys,time
import joblib,numpy as np,pandas as pd,sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];RELEASE=ROOT/'outputs/private/releases/20261007'
PRIVATE=RELEASE/'outputs/private';OUT=ROOT/'outputs/private/weather_fallback_20261009_v1'
GROUP_RUN=ROOT/'outputs/private/ice_group_balanced_20261009_v1'
GATE=ROOT/'outputs/private/ice_bottleneck_review_20261009_v1'
sys.path.insert(0,str(ROOT))
from scripts.baseline_ice_logistic import FEATURES
from src.external_temperature import fit_weather_temperature
from src.external_reserved import verify_reserved_freeze
from src.frozen_assessment import verify_freeze

PARAMS=dict(learning_rate=.05,max_iter=100,max_leaf_nodes=15,min_samples_leaf=100,
    l2_regularization=10.,early_stopping=False,random_state=20260923)
PLAN={'experiment_id':'20261009_weather_only_ridge_hgb_fixed_nested_v1',
    'permitted_outcome_period_kst':['2024-11-01','2025-02-28'],
    'scope':'Repeated first-winter development; not new blind or official validation.',
    'baseline':'Frozen competition14-only Ridge alpha100 weather component, predictions independently reproduced.',
    'candidates':['augmented_ridge','augmented_hgb'],'features':FEATURES,
    'ridge_alpha':100.,'hgb_parameters':PARAMS,'max_compute_threads':2,
    'training_domain':'Finite road temperature and nonmissing ASOS air temperature. Same rows for both candidates.',
    'training_weights':'No sample weighting: identical existing temperature row policy; no label-dependent subsampling.',
    'folds':'Exclude all outer group and inner validation group stations from training/preprocessing. Competition14 always available.',
    'selection':'Each candidate must improve inner station macro MAE and RMSE versus fixed baseline; every inner station MAE <= baseline*1.05. Choose smallest macro MAE then RMSE then candidate name.',
    'candidate_controls':'Report both prespecified outer candidates even when not selected, without post-outer choice or parameter search.',
    'banned_predictors':['station','road_temp','ice','state_raw','near_road_temp','neighbor_road_temp','near_state_*'],
    'stress':'Carry previous other-group donor weights unchanged; original, 30/60min delay with max60min age, 06to08 outage, no reference. No stress-based retuning.',
    'protected_or_reserved_outcomes_used':False,'frozen_evaluation_change_allowed':False,
    'runtime_versions':{'sklearn':sklearn.__version__,'numpy':np.__version__,'pandas':pd.__version__}}

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def validate_features(names):
    if list(names)!=FEATURES:raise ValueError('Only pinned weather14 predictors allowed')

def training_mask(frame,forbidden):
    return frame.road_temp.notna()&frame.asos_air_temp.notna()&~frame.station.isin(forbidden)

def regression(y,p):
    valid=np.isfinite(y)&np.isfinite(p);err=np.asarray(p)[valid]-np.asarray(y)[valid]
    return dict(n=int(valid.sum()),mae=float(np.abs(err).mean()),rmse=float(np.sqrt(np.mean(err**2))),bias=float(err.mean()))

def report(frame,prediction):
    p=np.asarray(prediction);valid=np.isfinite(frame.road_temp)&np.isfinite(p)
    rows={}
    for st in sorted(frame.station.unique()):
        mask=valid&frame.station.eq(st).to_numpy()
        rows[st]=regression(frame.road_temp.to_numpy()[mask],p[mask])
    return {'pooled':regression(frame.road_temp.to_numpy(),p),'stations':rows,
        'station_macro':{m:float(np.mean([r[m] for r in rows.values()])) for m in ['mae','rmse','bias']}}

def choose(reports):
    base=reports['baseline'];eligible=[]
    for candidate in PLAN['candidates']:
        r=reports[candidate]
        if r['pooled']['n']!=base['pooled']['n'] or set(r['stations'])!=set(base['stations']):raise ValueError('Different comparison population')
        if any(r['stations'][s]['n']!=base['stations'][s]['n'] for s in base['stations']):raise ValueError('Different station rows')
        improvement=all(r['station_macro'][m]<base['station_macro'][m]-1e-12 for m in ['mae','rmse'])
        safe=all(r['stations'][s]['mae']<=base['stations'][s]['mae']*1.05+1e-12 for s in base['stations'])
        if improvement and safe:eligible.append(candidate)
    return min(eligible,key=lambda c:(reports[c]['station_macro']['mae'],reports[c]['station_macro']['rmse'],c)) if eligible else 'baseline'

def predict(model,x):
    p=model.predict(x[FEATURES]);return np.where(x.asos_air_temp.notna(),p,np.nan)

def stress(combined,features):
    features=features.set_index(['station','time']);keys=pd.MultiIndex.from_frame(combined[['station','time']])
    current=features.loc[keys];original=current.neighbor_road_temp.to_numpy()
    rows=[];coverage=[]
    for scenario in ['original','30min_delivery_delay','60min_delivery_delay','network_outage_06to08','no_reference']:
        if 'delivery_delay' in scenario:
            lag=30 if scenario.startswith('30') else 60
            old=features.reindex(pd.MultiIndex.from_arrays([combined.station,combined.time-pd.Timedelta(minutes=lag)]))
            age=old.neighbor_age_minutes.to_numpy()+lag
            donor=np.where(np.isfinite(age)&(age>0)&(age<=60),old.neighbor_road_temp,np.nan)
        elif scenario=='network_outage_06to08':donor=np.where(combined.time.dt.hour.between(6,7),np.nan,original)
        elif scenario=='no_reference':donor=np.full(len(combined),np.nan)
        else:donor=original
        valid=np.isfinite(combined.road_temp)&np.isfinite(combined.baseline_weather)&np.isfinite(combined.selected_weather)
        coverage.append({'scenario':scenario,'shared_valid_rows':int(valid.sum()),'available_reference_rows':int((valid&np.isfinite(donor)).sum())})
        for variant in ['baseline_weather','selected_weather','baseline_gate','selected_gate']:
            weather=combined.baseline_weather.to_numpy() if variant.startswith('baseline') else combined.selected_weather.to_numpy()
            p=np.where(np.isfinite(donor),(1-combined.donor_weight)*weather+combined.donor_weight*donor,weather) if variant.endswith('gate') else weather
            assert np.array_equal(np.isfinite(p),np.isfinite(combined.baseline_weather))
            populations=[('all',valid),('observed_minus2_to2',valid&combined.road_temp.between(-2,2)),
                *[(st,valid&combined.station.eq(st)) for st in sorted(combined.station.unique())]]
            for population,mask in populations:
                rows.append({'scenario':scenario,'variant':variant,'population':population,**regression(combined.road_temp.to_numpy()[mask],np.asarray(p)[mask])})
    pd.DataFrame(rows).to_csv(OUT/'stress_metrics.csv',index=False);pd.DataFrame(coverage).to_csv(OUT/'stress_coverage.csv',index=False)
    return pd.DataFrame(rows).query("population == 'all'").to_dict('records')

def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='새 outputs/private 결과 폴더. 원본 실험은 덮어쓰지 않습니다.')
    args=parser.parse_args();OUT=args.output.resolve()
    if not OUT.is_relative_to((ROOT/'outputs/private').resolve()):
        parser.error('분석 결과는 outputs/private 안에만 저장합니다.')
    if OUT.exists():raise FileExistsError('Preserve completed/failed version; new version required')
    validate_features(FEATURES)
    frozen=verify_reserved_freeze(RELEASE,PRIVATE/'external_reserved_predictions_v1');original=verify_freeze(RELEASE)
    OUT.mkdir();write(OUT/'experiment_plan.json',PLAN);shutil.copy2(__file__,OUT/'analysis_source.py')
    paths={'development_index':GROUP_RUN/'development_index.parquet','feature_matrix':GROUP_RUN/'feature_matrix.parquet',
        'thermal':PRIVATE/'point_sources/rwis.parquet','external_features':PRIVATE/'external_development_features_v1/features.parquet',
        'gate_predictions':GATE/'temperature_gate_predictions.parquet',
        'baseline_model':PRIVATE/'external_temperature_nested_v1/baseline/model.joblib',
        'baseline_manifest':PRIVATE/'external_temperature_nested_v1/baseline/fit_manifest.json',
        'groups':RELEASE/'config/kma_external_validation_plan.json'}
    signature={k:{'path':str(p),'sha256':sha(p)} for k,p in paths.items()}
    write(OUT/'input_signature.json',signature)
    index=pd.read_parquet(paths['development_index']);x=pd.read_parquet(paths['feature_matrix'])[FEATURES]
    groups={g:set(v) for g,v in read(paths['groups'])['station_groups'].items()};external=set().union(*groups.values())
    from src.thermal_ice import validate_development
    index=validate_development(index)
    donor_ids=set(index[index.group.eq('competition')].station);assert len(donor_ids)==14
    thermal=pd.read_parquet(paths['thermal'],columns=['station','time','road_temp'])
    thermal=thermal[thermal.time.ge('2024-11-01')&thermal.time.lt('2025-03-01')];assert set(thermal.station)==donor_ids
    feature=pd.read_parquet(paths['external_features']);gate=pd.read_parquet(paths['gate_predictions'])
    assert set(feature.station)==external and set(gate.station)==external
    assert feature.time.ge('2024-11-01').all() and feature.time.lt('2025-03-01').all()
    outcomes=pd.concat([thermal,feature[['station','time','road_temp']]],ignore_index=True)
    assert not outcomes.duplicated(['station','time']).any()
    frame=index[['station','time','group']].merge(outcomes,on=['station','time'],how='left',validate='one_to_one')
    assert len(frame)==len(index)==len(x)
    frame=pd.concat([frame,x],axis=1)
    frame[['station','time','group','road_temp']].to_parquet(OUT/'training_index.parquet',index=False,compression='zstd')
    x.to_parquet(OUT/'weather_features.parquet',index=False,compression='zstd')
    baseline_info=read(paths['baseline_manifest']);assert baseline_info['features']==FEATURES and set(baseline_info['training_stations'])==donor_ids
    assert sha(paths['baseline_model'])==baseline_info['model_sha256']
    baseline=joblib.load(paths['baseline_model']);base_predictions=predict(baseline,x)
    outside=frame.station.isin(external)
    ordered=gate.set_index(['station','time']).loc[pd.MultiIndex.from_frame(frame.loc[outside,['station','time']])]
    expected=ordered.baseline_temperature_c.to_numpy()*2-feature.set_index(['station','time']).loc[ordered.index].neighbor_road_temp.to_numpy()
    assert np.allclose(base_predictions[outside],expected,equal_nan=True,rtol=0,atol=1e-10)
    assert np.array_equal(frame.loc[outside,'road_temp'].to_numpy(),ordered.road_temp.to_numpy(),equal_nan=True)
    frame['baseline_weather']=base_predictions;fits=[];cache={};decisions={};results=[]
    def fit(candidate,forbidden,folder):
        mask=training_mask(frame,forbidden);train=frame.loc[mask]
        assert not set(train.station)&set(forbidden)
        ident=hashlib.sha256(pd.util.hash_pandas_object(train[['station','time','road_temp']],index=True).to_numpy().tobytes()).hexdigest()
        key=(candidate,ident);folder.mkdir(parents=True)
        if key in cache:
            origin=cache[key];shutil.copy2(origin/'model.joblib',folder/'model.joblib');model=joblib.load(folder/'model.joblib');elapsed=0.
        else:
            started=time.monotonic()
            if candidate=='augmented_ridge':model,fitted=fit_weather_temperature(train,FEATURES,100.);assert len(fitted)==len(train)
            else:model=HistGradientBoostingRegressor(**PARAMS).fit(train[FEATURES],train.road_temp)
            elapsed=time.monotonic()-started;joblib.dump(model,folder/'model.joblib')
        receipt={'candidate':candidate,'training_identity':ident,'training_rows':len(train),'training_stations':sorted(set(train.station)),
            'forbidden_stations':sorted(forbidden),'features':FEATURES,'model_sha256':sha(folder/'model.joblib'),
            'model_path':str(folder.relative_to(OUT)/'model.joblib'),'fit_seconds':elapsed,
            'cache_reused_from':str(cache[key].relative_to(OUT)) if key in cache else None,
            'preprocessing_fit_on_training_only':True,'reserved_or_protected_outcomes_used':False}
        write(folder/'fit_manifest.json',receipt);cache.setdefault(key,folder);fits.append(receipt)
        return model
    with threadpool_limits(limits=2):
        for outer,held in groups.items():
            folder=OUT/outer;folder.mkdir();other=external-held;query=frame.loc[frame.station.isin(other)]
            reports={'baseline':report(query,query.baseline_weather)};oofs=[]
            for candidate in PLAN['candidates']:
                score=pd.Series(np.nan,index=query.index)
                for check,checked in groups.items():
                    if check==outer:continue
                    model=fit(candidate,held|checked,folder/'inner'/check/candidate)
                    mask=frame.station.isin(checked);score.loc[frame.index[mask]]=predict(model,frame.loc[mask])
                    print(outer,candidate,check,'inner_complete',flush=True)
                assert np.array_equal(np.isfinite(score),query.asos_air_temp.notna())
                reports[candidate]=report(query,score.to_numpy())
                part=query[['station','time','road_temp','baseline_weather']].copy();part['candidate']=candidate;part['prediction']=score.to_numpy();oofs.append(part)
            selected=choose(reports)
            decision={'outer_group':outer,'selection_groups':sorted(set(groups)-{outer}),'selected_candidate':selected,'reports':reports,
                'outer_labels_used_for_selection':False,'rule':PLAN['selection']}
            write(folder/'decision.json',decision);pd.concat(oofs,ignore_index=True).to_parquet(folder/'inner_oof.parquet',index=False)
            # 제외한 그룹의 예측 전에 다른 그룹만 사용한 선택 기록을 먼저 저장한다.
            heldmask=frame.station.isin(held);part=frame.loc[heldmask,['station','time','group','road_temp','baseline_weather']].copy()
            for candidate in PLAN['candidates']:
                model=fit(candidate,held,folder/'outer_models'/candidate)
                part[candidate]=predict(model,frame.loc[heldmask])
            part['selected_candidate']=selected;part['selected_weather']=part.baseline_weather if selected=='baseline' else part[selected]
            part.to_parquet(folder/'outer_predictions.parquet',index=False);results.append(part);decisions[outer]=decision
            print(outer,selected,'outer_complete',flush=True)
    combined=pd.concat(results,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    weight=gate.set_index(['station','time']).loc[pd.MultiIndex.from_frame(combined[['station','time']])].donor_weight
    combined['donor_weight']=weight.to_numpy()
    metrics={v:report(combined,combined[v]) for v in ['baseline_weather','augmented_ridge','augmented_hgb','selected_weather']}
    assert {r['pooled']['n'] for r in metrics.values()}=={155236}
    combined.to_parquet(OUT/'outer_predictions.parquet',index=False,compression='zstd')
    stations=[];regimes=[]
    for variant,r in metrics.items():
        stations.extend({'station':s,'variant':variant,**m} for s,m in r['stations'].items())
        for regime,mask in [('all',np.ones(len(combined),bool)),('day_06to18',combined.time.dt.hour.between(6,17)),
            ('night',~combined.time.dt.hour.between(6,17)),('observed_minus2_to2',combined.road_temp.between(-2,2)),
            *[(g,combined.group.eq(g)) for g in groups]]:
            regimes.append({'variant':variant,'regime':regime,**regression(combined.road_temp.to_numpy()[mask],combined[variant].to_numpy()[mask])})
    pd.DataFrame(stations).to_csv(OUT/'station_metrics.csv',index=False);pd.DataFrame(regimes).to_csv(OUT/'regime_metrics.csv',index=False)
    stress_overall=stress(combined,feature)
    write(OUT/'fit_receipts.json',fits);write(OUT/'decisions.json',decisions)
    assert verify_reserved_freeze(RELEASE,PRIVATE/'external_reserved_predictions_v1')==frozen and verify_freeze(RELEASE)==original
    summary={'status':'first_winter_weather_fallback_nested_comparison_complete','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'metrics':metrics,'choices':{g:d['selected_candidate'] for g,d in decisions.items()},'stress_overall':stress_overall,
        'fit_calls':len(fits),'unique_fits':len(cache),'feature_count':len(FEATURES),'input_rows':len(frame),
        'scope':PLAN['scope'],'protected_or_reserved_outcomes_used':False,'frozen_models_modified':False,
        'frozen_external_files':len(frozen['files']),'frozen_original_files':len(original['files']),
        'files':{p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file()}}
    write(OUT/'summary.json',summary)
    print(json.dumps({'status':summary['status'],'choices':summary['choices'],'metrics':{k:{q:v[q] for q in ['pooled','station_macro']} for k,v in metrics.items()},
        'fit_calls':len(fits),'unique_fits':len(cache)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
