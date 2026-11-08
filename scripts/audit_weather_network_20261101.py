"""AWS 공간 결합을 별도 merge_asof로 재계산하고 36모형·6재학습을 검산한다."""
import gc
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved
from scripts.audit_road_weather_transfer import compare,measure
from scripts.audit_weather_temporal import bootstrap
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network

FIELDS=['air_temp','humidity','wind_speed','rain_15m','dewpoint']
TARGET_FIELDS=dict(zip(['air_temperature','relative_humidity','wind_speed'],FIELDS[:3]))


def independent_features(f,plan,out):
    source=ROOT/plan['weather_sources']
    aws=pd.read_parquet(source/'aws.parquet',columns=['station','source_time',*FIELDS])
    coords=pd.read_csv(source/'weather_coordinates.csv',dtype={'station_id':str})
    coords=coords.loc[coords.kind.eq('AWS')].set_index('station_id')
    coords['lat']=coords.latitudes.astype(float);coords['lon']=coords.longitudes.astype(float)
    target=pd.read_csv(ROOT/plan['target_coordinates'],dtype={'station':str}).set_index('station')
    cached=pd.read_parquet(out/'network_features.parquet')
    receipt=read(out/'network_receipt.json');assert sha(out/'network_features.parquet')==receipt['feature_sha256']
    checked=0;maximum=0.;joined_rows=0
    for station,q in f.groupby('station',sort=True):
        lat,lon=np.deg2rad(target.loc[station,['requested_lat','requested_lon']].to_numpy(float))
        b=np.deg2rad(coords.lat.to_numpy());d=np.deg2rad(coords.lon.to_numpy())
        distance=6371.0088*2*np.arcsin(np.sqrt(np.sin((b-lat)/2)**2+np.cos(lat)*np.cos(b)*np.sin((d-lon)/2)**2))
        selected=sorted((float(dist),sid) for sid,dist in zip(coords.index,distance)
            if sid in set(aws.station) and dist<=plan['network']['radius_km'])[:plan['network']['neighbours']]
        recorded=receipt['mapping'][station]['candidates']
        assert [r['station'] for r in recorded]==[s for _,s in selected]
        np.testing.assert_allclose([r['distance_km'] for r in recorded],[d for d,_ in selected],rtol=1e-12,atol=1e-10)
        combined=[];dist=[];weight=[]
        for distance,sid in selected:
            raw=aws.loc[aws.station.eq(sid),['source_time',*FIELDS]].sort_values('source_time')
            z=pd.merge_asof(q[['time']].sort_values('time'),raw,left_on='time',right_on='source_time',
                allow_exact_matches=False,direction='backward',tolerance=pd.Timedelta(minutes=plan['network']['max_age_minutes']))
            available=z.source_time.notna()
            ages=(z.time-z.source_time).dt.total_seconds()/60
            assert ages.loc[available].gt(0).all() and ages.loc[available].le(15).all()
            combined.append(z[FIELDS].to_numpy());dist.append(distance)
            weight.append(1/max(distance,plan['network']['distance_floor_km'])**plan['network']['power'])
            joined_rows+=int(available.sum())
        values=np.stack(combined,axis=1);dist=np.asarray(dist);weight=np.asarray(weight)
        reference={}
        for j,field in enumerate(FIELDS):
            a=values[:,:,j];ok=np.isfinite(a);w=ok*weight
            total=np.sum(w,axis=1);count=ok.sum(axis=1);have=count>0
            normalized=np.divide(w,total[:,None],out=np.zeros_like(w),where=have[:,None])
            mean=np.full(len(q),np.nan)
            mean[have]=np.sum(np.where(ok,a,0)*w,axis=1)[have]/total[have]
            sd=np.full(len(q),np.nan)
            sd[have]=np.sqrt(np.sum(np.where(ok,a-mean[:,None],0)**2*w,axis=1)[have]/total[have])
            span=np.full(len(q),np.nan)
            span[have]=(np.max(np.where(ok,a,-np.inf),axis=1)-np.min(np.where(ok,a,np.inf),axis=1))[have]
            effective=np.full(len(q),np.nan);effective[have]=1/np.sum(normalized**2,axis=1)[have]
            weighted_distance=np.full(len(q),np.nan);weighted_distance[have]=np.sum(w*dist,axis=1)[have]/total[have]
            prefix='network_'+field+'_'
            reference.update({prefix+'idw':mean,prefix+'sd':sd,prefix+'range':span,
                prefix+'contrast':mean-q['aws_'+field].to_numpy(float),prefix+'count':count,
                prefix+'distance_km':weighted_distance,prefix+'effective_n':effective})
        for column,a in reference.items():
            b=cached.loc[q.index,column].to_numpy()
            np.testing.assert_allclose(a,b,rtol=1e-12,atol=1e-10,equal_nan=True)
            finite=np.isfinite(a)&np.isfinite(b)
            if finite.any():maximum=max(maximum,float(np.abs(a[finite]-b[finite]).max()))
            checked+=len(a)
    return cached,dict(feature_values_checked=checked,maximum_feature_difference=maximum,joined_source_rows=joined_rows)


def report(p,column):
    return dict(pooled=measure(p,column),winters={str(y):measure(q,column) for y,q in p.groupby('winter')},
        regions={g:measure(q,column) for g,q in p.groupby('group')},cold=measure(p.loc[p.cold_input],column))


def constrain(p,target):
    if target=='relative_humidity':return np.clip(p,0,100)
    if target=='wind_speed':return np.maximum(p,0)
    return p


def main():
    plan=read(ROOT/'config/weather_network_20261101.json');out=ROOT/plan['output']
    if (out/'independent_verification.json').exists():raise FileExistsError('Preserve completed network verification')
    frozen=read(out/'plan.json');summary=read(out/'summary.json')
    for p,h in frozen['signatures'].items():assert sha(ROOT/p)==h,p
    for p,h in summary['files'].items():assert sha(out/p)==h,p
    assert verify_preserved()==frozen['preservation']==summary['preservation']
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations']) and not {'ice','road_temp','state_raw'}&set(f)
    network,quality=independent_features(f,plan,out)
    base=pd.read_parquet(ROOT/plan['spatial_baseline']/'features.parquet')
    stable=pd.read_parquet(ROOT/plan['stable_history']/'features.parquet')
    predictions_checked=0;metric_checks=0;refits=[];checks={}
    for target,modes in summary['reports'].items():
        field=TARGET_FIELDS[target]
        asos=f['asos_'+field].where((f.asos_age_minutes>0)&(f.asos_age_minutes<=60)).to_numpy()
        aws=f['aws_'+field].where((f.aws_age_minutes>0)&(f.aws_age_minutes<=15)).to_numpy()
        nearest=np.where(np.isfinite(aws),aws,asos)
        valid=np.isfinite(f[target])&np.isfinite(asos)&np.isfinite(nearest)
        current_x=stable if target=='relative_humidity' else base
        x=pd.concat([current_x,network],axis=1);checks[target]={}
        for mode,record in modes.items():
            folder=out/target/mode;p=pd.read_parquet(folder/'predictions.parquet')
            expect=f.loc[valid&f.group.ne('competition')]
            pd.testing.assert_frame_equal(p[['station','time','group','winter']],expect[['station','time','group','winter']].reset_index(drop=True),check_exact=True)
            np.testing.assert_array_equal(p.observed,expect[target]);np.testing.assert_array_equal(p.asos,asos[expect.index])
            np.testing.assert_array_equal(p.aws_fallback,nearest[expect.index])
            np.testing.assert_array_equal(p.cold_input,np.abs(expect.asos_air_temp)<=3)
            for spec in [s for s in summary['fits'] if s['target']==target and s['mode']==mode]:
                held=spec['held'];year=spec['query_winter'];train=valid&f.group.ne(held);query=valid&f.group.eq(held)
                if year is not None:train&=f.winter.ne(year);query&=f.winter.eq(year)
                assert not set(f.loc[train,'station'])&set(f.loc[query,'station'])
                if year is not None:assert set(f.loc[train,'winter'])=={2025 if year==2024 else 2024}
                assert int(train.sum())==spec['training_rows'] and int(query.sum())==spec['query_rows']
                assert sorted(f.loc[train,'station'].unique())==spec['training_stations'] and list(x)==spec['features']
                stem=held+('_'+str(year) if year is not None else '')
                model_path=folder/(stem+'.joblib');reference=ROOT/spec['reference_model']
                assert sha(model_path)==spec['model_sha256'] and sha(reference)==spec['reference_model_sha256']
                models=[joblib.load(reference),joblib.load(model_path)]
                for model,column,predictors in zip(models,['current','network_residual'],[current_x,x]):
                    with deny_network() as attempts,threadpool_limits(limits=2):a=constrain(model.predict(predictors.loc[query])+nearest[query],target)
                    assert not attempts
                    q=p.loc[p.group.eq(held)]
                    if year is not None:q=q.loc[q.winter.eq(year)]
                    np.testing.assert_array_equal(a,q[column]);predictions_checked+=len(a)
                np.testing.assert_array_equal(np.load(model_path.with_suffix('.npy'),allow_pickle=False),a)
                if held=='honam_baekyang' and year in [2024,None]:
                    counts=f.loc[train].groupby(['station','winter']).station.transform('size').to_numpy(float)
                    weights=1/counts;weights/=weights.mean();model=HistGradientBoostingRegressor(**plan['model'])
                    with deny_network() as attempts,threadpool_limits(limits=2):
                        model.fit(x.loc[train],f.loc[train,target].to_numpy()-nearest[train],sample_weight=weights)
                        repeated=constrain(model.predict(x.loc[query])+nearest[query],target)
                    assert not attempts;np.testing.assert_array_equal(repeated,a)
                    refits.append(dict(target=target,mode=mode,held=held,query_winter=year,exact=True))
                del models;gc.collect();pa.default_memory_pool().release_unused()
            for column,expected in record['metrics'].items():metric_checks+=compare(report(p,column),expected)
            boot=bootstrap(p,'network_residual','current',plan['bootstrap']);metric_checks+=compare(boot,record['bootstrap'])
            c=report(p,'network_residual');b=report(p,'current');g=plan['gates']
            gates=dict(pooled=c['pooled']['mae']<=b['pooled']['mae']*(1-g['minimum_mae_reduction']),
                both_winters=all(c['winters'][y]['mae']<=v['mae']*g['maximum_winter_mae_ratio'] for y,v in b['winters'].items()),
                every_region=all(c['regions'][k]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for k,v in b['regions'].items()),
                cold=c['cold']['mae']<=b['cold']['mae']*g['maximum_cold_mae_ratio'],date_sensitivity=boot['quantiles'][2]<0)
            assert gates==record['gates'] and all(gates.values())==record['primary_success'];checks[target][mode]=all(gates.values())
            print('AUDIT',target,mode,flush=True)
        del x;gc.collect();pa.default_memory_pool().release_unused()
    assert len(refits)==6 and [t for t,m in checks.items() if all(m.values())]==summary['accepted_targets']
    assert verify_preserved()==summary['preservation']
    write(out/'independent_verification.json',dict(status='passed',summary_sha256=sha(out/'summary.json'),
        **quality,predictions_checked=predictions_checked,metric_checks=metric_checks,refits=refits,
        accepted_targets_verified=summary['accepted_targets'],protected_outcomes_read=False,new_independent_assessment=False))
    print('PASSED',quality,predictions_checked,metric_checks,flush=True)


if __name__=='__main__':main()
