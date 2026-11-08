from pathlib import Path
import sys,json,zipfile,time,gc
import numpy as np,pandas as pd,joblib
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from src.data_source import sha256_file as sha
from src.wind_direction_terrain_20261106 import direction_features,terrain_features
from src.weather_features import haversine_km
from src.road_weather_transfer import features,baselines,constrain,balanced_weights
from scripts.evaluate_weather_history_spatial_20261101 import report
from scripts.evaluate_weather_space_time import sensitivity
from src.offline_runtime import deny_network
P=ROOT/'outputs/private';OUT=P/'wind_direction_terrain_20261106_v1'
CONFIG=ROOT/'config/wind_direction_terrain_20261106.json'

def prepare(f):
    rows=[]
    with zipfile.ZipFile(ROOT/'DATA AI 경진대회 데이터(20261007).zip') as z:
        for n in z.namelist():
            if 'ASOS' not in n or not n.endswith('.csv'):continue
            q=pd.read_csv(z.open(n),usecols=['시간','지점','풍속(m/s)','풍향(16방위)'],dtype={'지점':str})
            q.columns=['source_time','source_station','raw_speed','raw_direction'];q.source_time=pd.to_datetime(q.source_time)
            q=q.loc[q.source_time.dt.strftime('%Y-%m-%d').eq(n.rsplit('_',1)[1][:-4])];rows.append(q)
    raw=pd.concat(rows,ignore_index=True)
    assert not raw.duplicated(['source_station','source_time']).any()
    coords=pd.read_csv(P/'releases/20261007/outputs/private/point_sources/weather_coordinates.csv',dtype={'station_id':str})
    coords=coords.loc[coords.kind.eq('ASOS')&coords.station_id.isin(raw.source_station)].set_index('station_id')
    tc=pd.read_csv(P/'reanalysis_development_20261031_v1/grid_mapping.csv',dtype={'station':str}).set_index('station')
    mapping={};parts=[]
    for station,q in f.groupby('station',sort=True):
        lat,lon=tc.loc[station,['requested_lat','requested_lon']]
        dist,sid=min((haversine_km(lat,lon,float(r.latitudes),float(r.longitudes)),sid) for sid,r in coords.iterrows())
        np.testing.assert_allclose(q.asos_distance_km,dist,rtol=1e-12,atol=1e-10)
        key=q[['time','asos_age_minutes']].copy();key['idx']=q.index
        key['source_time']=key.time-pd.to_timedelta(key.asos_age_minutes,unit='m');key['source_station']=sid
        key=key.merge(raw,on=['source_station','source_time'],how='left',validate='many_to_one').set_index('idx').sort_index()
        good=q.asos_age_minutes.between(0,60,inclusive='right')
        np.testing.assert_allclose(key.loc[good,'raw_speed'],q.loc[good,'asos_wind_speed'],equal_nan=True)
        d,a=direction_features(key.raw_direction.where(good),q.asos_wind_speed.where(good))
        terrain=pd.read_csv(P/'terrain_thermal_data_20261024_v1/station_terrain.csv',dtype={'station':str}).set_index('station')
        t=terrain_features(q.station,a,q.asos_wind_speed,terrain);parts.append(pd.concat([d,t],axis=1));mapping[station]=dict(asos=sid,distance_km=dist)
    extra=pd.concat(parts).sort_index();assert extra.index.equals(f.index) and extra.shape==(len(f),15)
    extra.to_parquet(OUT/'features.parquet',index=False,compression='zstd')
    write(OUT/'feature_receipt.json',dict(rows=len(f),columns=list(extra),sha256=sha(OUT/'features.parquet'),mapping=mapping,
        raw_direction_is_public_weather=True,other_road_state_read=False,source_times_strictly_before_target=True,
        datum='Copernicus DSM metre proxy; not normalized provided DEM or road deck height',
        calm_code_0_not_north=True,minimum_direction_speed=.5,unknown_fraction=float(extra.direction_missing.mean())))
    return extra

def main():
    plan=read(CONFIG);assert not OUT.exists();OUT.mkdir()
    paths=[CONFIG,Path(__file__),ROOT/'src/wind_direction_terrain_20261106.py',ROOT/plan['input'],P/'weather_network_20261101_v1/summary.json',P/'terrain_thermal_data_20261024_v1/station_terrain.csv']
    frozen=verify_preserved();write(OUT/'plan.json',dict(at_utc=now(),settings=plan,signatures={p.relative_to(ROOT).as_posix():sha(p) for p in paths},preservation=frozen))
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not {'ice','road_temp','state_raw'}&set(f) and not set(f.station)&set(plan['blocked_stations'])
    extra=prepare(f);base=pd.concat([features(f),pd.read_parquet(P/'weather_network_20261101_v1/network_features.parquet')],axis=1)
    assert base.shape[1]==69
    asos,nearest=baselines(f,'wind_speed');valid=np.isfinite(f.wind_speed)&np.isfinite(asos)&np.isfinite(nearest)
    assert int(valid.sum())==447628
    groups=sorted(set(f.group)-{'competition'});reports={};fits=[]
    for mode in ['joint','spatial']:
        folder=OUT/mode;folder.mkdir();parts=[]
        for year in ([2024,2025] if mode=='joint' else [None]):
            for held in groups:
                train=valid&f.group.ne(held);query=valid&f.group.eq(held)
                if year is not None:train&=f.winter.ne(year);query&=f.winter.eq(year)
                assert not set(f.loc[train,'station'])&set(f.loc[query,'station'])
                stem=held+('_'+str(year) if year else '')
                ref=P/'weather_network_20261101_v1/wind_speed'/mode/(stem+'.joblib');m=read(ref.with_suffix('.json'));assert sha(ref)==m['model_sha256']
                with deny_network() as attempts,threadpool_limits(limits=2):
                    old=constrain(joblib.load(ref).predict(base.loc[query])+nearest[query],'wind_speed')
                assert not attempts;np.testing.assert_array_equal(old,np.load(ref.with_suffix('.npy'),allow_pickle=False))
                p=f.loc[query,['station','time','group','winter']].copy();p['observed']=f.loc[query,'wind_speed'];p['current']=old;p['cold_input']=np.abs(f.loc[query,'asos_air_temp'])<=3
                for candidate in ['direction','terrain']:
                    x=pd.concat([base,extra.iloc[:,:6] if candidate=='direction' else extra],axis=1)
                    started=time.perf_counter();model=HistGradientBoostingRegressor(**plan['model'])
                    with deny_network() as attempts,threadpool_limits(limits=2):
                        model.fit(x.loc[train],f.loc[train,'wind_speed'].to_numpy()-nearest[train],sample_weight=balanced_weights(f.loc[train]))
                        pred=constrain(model.predict(x.loc[query])+nearest[query],'wind_speed')
                    assert not attempts and np.isfinite(pred).all()
                    path=folder/(stem+'_'+candidate+'.joblib');joblib.dump(model,path,compress=3);np.save(path.with_suffix('.npy'),pred,allow_pickle=False)
                    record=dict(mode=mode,held=held,winter=year,candidate=candidate,training_rows=int(train.sum()),query_rows=int(query.sum()),
                        train_stations=sorted(set(f.loc[train,'station'])),query_stations=sorted(set(f.loc[query,'station'])),features=list(x),
                        model_sha256=sha(path),prediction_sha256=sha(path.with_suffix('.npy')),seconds=time.perf_counter()-started)
                    write(path.with_suffix('.json'),record);fits.append(record);p[candidate]=pred
                    print('FIT',len(fits),'/24',mode,held,year,candidate,round(record['seconds'],1),flush=True);del model,x;gc.collect()
                p['terrain_blend']=(p.terrain+p.current)/2;parts.append(p)
        p=pd.concat(parts).sort_values(['station','time']).reset_index(drop=True);assert not p.duplicated(['station','time']).any();p.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
        measures={c:report(p,c) for c in ['current','direction','terrain','terrain_blend']};reports[mode]={}
        for c in ['direction','terrain','terrain_blend']:
            boot=sensitivity(p,c,'current',plan['bootstrap']);a=measures[c];b=measures['current'];g=plan['gates']
            gates=dict(pooled=a['pooled']['mae']<=b['pooled']['mae']*(1-g['minimum_mae_reduction']),both_winters=all(a['winters'][y]['mae']<=v['mae'] for y,v in b['winters'].items()),every_region=all(a['regions'][r]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for r,v in b['regions'].items()),cold=a['cold']['mae']<=b['cold']['mae'],date_sensitivity=boot['quantiles'][2]<0)
            reports[mode][c]=dict(metrics=a,reference=b,bootstrap=boot,gates=gates,passed=all(gates.values()))
            print('REPORT',mode,c,b['pooled']['mae'],a['pooled']['mae'],gates,flush=True)
    accepted=[c for c in ['direction','terrain','terrain_blend'] if all(reports[m][c]['passed'] for m in reports)]
    assert len(fits)==24 and verify_preserved()==frozen
    write(OUT/'summary.json',dict(status='controlled_wind_direction_terrain_complete',reports=reports,accepted_candidates=accepted,fits=fits,
        protection=frozen,production_model_changed=False,protected_targets_used=False,new_independent_assessment=False,
        files={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file()}))
    print('COMPLETE accepted',accepted,flush=True)
if __name__=='__main__':main()