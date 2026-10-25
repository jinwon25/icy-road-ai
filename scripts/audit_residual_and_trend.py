"""잔차 모델 재학습·마진 항등식·독립 내부 지표와 인과적 외삽을 검산한다."""
from collections import Counter,defaultdict
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import xgboost as xgb
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.blind_icing_validation import DEFAULT,verify,read,write,now,old_freezes
from scripts.audit_icing_transition import independent_metrics

FEATURES=['asos_air_temp','asos_ground_temp','asos_humidity','asos_rain_mm','asos_snow_cm','asos_cloud_tenths','asos_solar_mj_m2',
          'asos_wind_speed','asos_dewpoint_obs','asos_pressure','asos_visibility','asos_new_snow3h','asos_soil5cm']


def xmatrix(f):
    x=f[FEATURES].copy();x['dewpoint_depression']=x.asos_air_temp-x.asos_dewpoint_obs;x['ground_dewpoint_gap']=x.asos_ground_temp-x.asos_dewpoint_obs
    return x


def weights(f,kind):
    if kind=='row':return np.ones(len(f))
    keys=[(s,int(w),t.date(),int(y)) for s,w,t,y in f[['station','winter','time','ice']].itertuples(index=False,name=None)]
    counts=Counter(keys);classes=defaultdict(set);dates=defaultdict(set)
    for s,w,d,y in counts:classes[s,w,d].add(y);dates[s,w].add(d)
    result=np.array([1/(counts[s,w,d,y]*len(classes[s,w,d])*len(dates[s,w])) for s,w,d,y in keys]);return result/result.mean()


def audit_selection(inner,table,choice,predict):
    checks=0
    for row in table.itertuples():
        pred=predict(inner,row)
        for year in ['all',2024,2025]:
            mask=np.ones(len(inner),bool) if year=='all' else inner.winter.eq(year).to_numpy();r=independent_metrics(inner.loc[mask],pred[mask])
            np.testing.assert_allclose(row.f1 if year=='all' else getattr(row,'f1_'+str(year)),r['f1_fixed_population'],rtol=0,atol=1e-12);checks+=1
            if year=='all':
                for k in ['precision','recall']:
                    np.testing.assert_allclose(getattr(row,k),r[k+'_available_station_mean'],rtol=0,atol=1e-12);checks+=1
                for s in sorted(inner.station.unique()):
                    m=inner.station.eq(s).to_numpy();actual=independent_metrics(inner.loc[m],pred[m])['f1_fixed_population']
                    np.testing.assert_allclose(getattr(row,'site_'+s),actual,rtol=0,atol=1e-12);checks+=1
    records=table.to_dict('records');base=next(r for r in records if r['candidate']=='asos_zero')
    eligible=[r for r in records if r['f1']>base['f1'] and r['f1']>=1.01*base['f1'] and all(r[c]>=base[c] for c in ['precision','recall','f1_2024','f1_2025',*[c for c in table if c.startswith('site_')]])]
    def best(rows):return min(rows,key=lambda r:(-r['f1'],r['complexity'],r['cap'],r['rounds'],r['candidate']))['candidate']
    assert (best(eligible) if eligible else 'asos_zero')==choice['guarded']
    assert best(records)==choice['maximum_f1']
    return checks


def main():
    verify(DEFAULT)
    for kind in ['residual','causal_trend']:
        config=ROOT/f'config/{kind}_icing_20261025.json' if kind=='residual' else ROOT/'config/causal_trend_20261025.json'
        plan=read(config);out=ROOT/plan['out']
        if (out/'audit.json').exists():raise FileExistsError('Preserve completed audit')
        summary=read(out/'summary.json')
        for name,digest in read(out/'plan.json')['signatures'].items():assert sha(ROOT/name)==digest,name
        f=pd.read_parquet(ROOT/plan['source']).sort_values(['station','time']).reset_index(drop=True)
        assert set(f.station).isdisjoint(plan['blocked_stations'])
        final=pd.read_parquet(out/'predictions.parquet');assert sha(out/'predictions.parquet')==summary['predictions_sha256']
        if kind=='residual':
            for i,fit in enumerate(summary['fits']):
                train=f.loc[~f.group.isin(fit['excluded'])&f.available&f.ice.isin([0,1])];q=f.loc[f.group.isin(fit['excluded'])]
                assert len(train)==fit['rows'] and int(train.ice.sum())==fit['positive_rows'] and sorted(train.station.unique())==fit['stations']
                assert set(train.station).isdisjoint(q.station);assert sha(out/fit['model_path'])==fit['model_sha256']
                b=-train.asos_air_temp.to_numpy(np.float32)/2 if fit['prior']=='temperature' else np.zeros(len(train),np.float32)
                qb=-q.asos_air_temp.fillna(0).to_numpy(np.float32)/2 if fit['prior']=='temperature' else np.zeros(len(q),np.float32)
                dtrain=xgb.DMatrix(xmatrix(train),label=train.ice,weight=weights(train,fit['weights']),base_margin=b,nthread=2)
                dq=xgb.DMatrix(xmatrix(q),base_margin=qb,nthread=2);dz=xgb.DMatrix(xmatrix(q),base_margin=np.zeros(len(q),np.float32),nthread=2)
                stored=xgb.Booster();stored.load_model(out/fit['model_path']);stored.set_param({'nthread':2,'device':'cpu'})
                saved=pd.read_parquet(out/('__'.join(fit['excluded'])+'__scores.parquet'))
                pd.testing.assert_frame_equal(saved[['station','time']].reset_index(drop=True),q[['station','time']].reset_index(drop=True))
                with deny_network() as attempts,threadpool_limits(limits=2):
                    reproduced=xgb.train(plan['parameters'],dtrain,num_boost_round=max(plan['rounds']))
                    for rounds in plan['rounds']:
                        a=reproduced.predict(dq,output_margin=True,iteration_range=(0,rounds));s=stored.predict(dq,output_margin=True,iteration_range=(0,rounds));z=stored.predict(dz,output_margin=True,iteration_range=(0,rounds))
                        np.testing.assert_array_equal(a,s);np.testing.assert_array_equal(s,saved[fit['model']+'_r'+str(rounds)])
                        # XGBoost는 각 나무를 float32로 누적한다. 시작값이 다르면
                        # 합산 반올림도 달라지므로 항등식에는 연산 수 기반 오차 한계를 쓴다.
                        unit=np.finfo(np.float32).eps/2;gamma=(rounds+2)*unit/(1-(rounds+2)*unit)
                        bound=gamma*(np.abs(qb)+2*rounds*plan['parameters']['eta']*plan['parameters']['max_delta_step'])+2*unit*np.abs(qb)
                        assert np.all(np.abs((s-z).astype(float)-qb)<=bound+1e-7)
                assert not attempts
                print('REPRODUCED',i+1,fit['model'],','.join(fit['excluded']),flush=True)
            specs={m['name']:m for m in plan['models']}
            def predict(q,row):
                air=q.asos_air_temp.to_numpy(float)
                if row.candidate=='asos_zero':return np.where(q.available,air<=0,np.nan)
                prior=-q.asos_air_temp.fillna(0).to_numpy(np.float32)/2 if specs[row.model]['prior']=='temperature' else 0
                correction=np.clip(2*(q[row.model+'_r'+str(row.rounds)].to_numpy(float)-prior),-row.cap,row.cap)
                if row.direction=='reject_only':correction=np.minimum(correction,0)
                return np.where(q.available,air<=correction,np.nan)
        else:
            source={}
            for s,t,air in f[['station','asos_source_time','asos_air_temp']].drop_duplicates().itertuples(index=False,name=None):
                if pd.notna(t):source[s,t]=air
            slopes=[]
            for s,t,st,air,age in final[['station','time','asos_source_time','asos_air_temp','asos_age_minutes']].itertuples(index=False,name=None):
                value=np.nan
                if pd.notna(st):
                    assert st<t and (t-st).total_seconds()/60==age
                    delta=air-source.get((s,st-pd.Timedelta(hours=1)),np.nan)
                    if 0<age<=60 and np.isfinite(delta) and abs(delta)<=10:value=delta
                slopes.append(value)
            np.testing.assert_array_equal(final.trend_c_per_hour,slopes)
            def predict(q,row):
                air=q.asos_air_temp.to_numpy(float)
                correction=np.clip(row.alpha*q.trend_c_per_hour.to_numpy(float)*q.asos_age_minutes.to_numpy(float)/60,-row.cap,row.cap)
                correction=np.nan_to_num(correction,nan=0)
                return np.where(q.available,air+correction<=0,np.nan)
        checks=0
        for choice in summary['selections']:
            held=choice['held']
            if kind=='residual':
                inner=pd.concat([pd.read_parquet(out/('__'.join(sorted([held,g]))+'__scores.parquet')).loc[lambda q:q.group.eq(g)] for g in sorted(final.group.unique()) if g!=held],ignore_index=True)
            else:inner=final.loc[~final.group.eq(held)]
            path=out/(held+'__inner.csv');assert sha(path)==choice['inner_sha256'];table=pd.read_csv(path)
            checks+=audit_selection(inner,table,choice['selected'],predict)
            q=final.loc[final.group.eq(held)]
            for row in table.itertuples():np.testing.assert_array_equal(predict(q,row),q[row.candidate])
            for track,name in choice['selected'].items():np.testing.assert_array_equal(q[track],q[name])
        write(out/'audit.json',dict(status='passed',at_utc=now(),summary_sha256=sha(out/'summary.json'),code_sha256=sha(Path(__file__)),
            retrained_models=len(summary.get('fits',[])),replayed_score_prefixes=2*len(summary.get('fits',[])),inner_metric_checks=checks,selection_checks=8,
            causal_trend_rows_checked=len(final) if kind=='causal_trend' else 0,new_four_site_outcomes_used=False))
        print('AUDIT PASSED',kind,checks,flush=True)
    verify(DEFAULT);assert old_freezes()==(47,549)


if __name__=='__main__':main()
