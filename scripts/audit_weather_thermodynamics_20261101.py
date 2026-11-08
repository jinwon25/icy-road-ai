"""124입력의 별도 수식·문맥 불변·24모형·4재학습·모든 지표와 봉인을 검산한다."""
import gc
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
from scipy.special import expit
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved
from scripts.audit_weather_history_spatial_20261101 import report
from scripts.audit_weather_temporal import bootstrap
from scripts.audit_road_weather_transfer import compare
from src.weather_thermodynamics import thermodynamic_features
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def independent_physical(frame):
    def es(t,ice=False):
        t=np.asarray(t,float);t=np.where((t>=-80)&(t<=60),t,np.nan)
        return 611.21*np.exp((22.587 if ice else 17.502)*(t-.01)/(t+(273.85 if ice else 240.96)))
    def fp(e):
        with np.errstate(divide='ignore',invalid='ignore'):
            ratio=np.log(np.where(e>0,e/611.21,np.nan))
            t=(273.85*ratio+.22587)/(22.587-ratio)
        return np.where(np.isfinite(t)&(t>=-80)&(t<=60),t,np.nan)
    output={};raw={}
    for source,dew,limit in [('asos','dewpoint_obs',60),('aws','dewpoint',15)]:
        good=(frame[source+'_age_minutes']>0)&(frame[source+'_age_minutes']<=limit)
        t=frame[source+'_air_temp'].where(good).to_numpy()
        rh=frame[source+'_humidity'].where(good).to_numpy()
        td=frame[source+'_'+dew].where(good).to_numpy()
        e=es(t)*np.where((rh>=0)&(rh<=100),rh/100,np.nan);point=fp(e)
        raw[source]=e
        for key,v in dict(liquid_saturation_pa=es(t),vapor_pressure_pa=e,saturation_deficit_pa=es(t)-e,
            frost_point_c=point,air_frost_gap_c=t-point,dewpoint_rh_disagreement_pct=100*es(td)/es(t)-rh,
            ice_saturation_deficit_pa=np.where(t<=0,es(t,True)-e,np.nan)).items():output[source+'_'+key]=v
    ground=frame.asos_ground_temp.where((frame.asos_age_minutes>0)&(frame.asos_age_minutes<=60)).to_numpy()
    output['asos_ground_condensation_pa']=raw['asos']-es(ground)
    output['asos_ground_frost_excess_pa']=np.where(ground<=0,raw['asos']-es(ground,True),np.nan)
    output['aws_asos_vapor_contrast_pa']=raw['aws']-raw['asos']
    output['aws_asos_frost_contrast_c']=output['aws_frost_point_c']-output['asos_frost_point_c']
    result=pd.DataFrame(output,index=frame.index)
    history=['asos_vapor_pressure_pa','asos_saturation_deficit_pa','aws_vapor_pressure_pa','aws_saturation_deficit_pa']
    added={}
    for hours in [3,24]:
        for field in history:
            for kind in ['mean','departure','coverage']:added[f'{field}_{kind}_{hours}h']=np.full(len(frame),np.nan)
    for _,part in frame.groupby(['station','winter']):
        idx=part.sort_values('time').index
        values=result.loc[idx,history].set_axis(pd.DatetimeIndex(frame.loc[idx,'time']))
        for hours,minimum in [(3,6),(24,48)]:
            mean=values.rolling(f'{hours}h',closed='right',min_periods=minimum).mean()
            count=values.rolling(f'{hours}h',closed='right',min_periods=0).count()
            for field in history:
                added[f'{field}_mean_{hours}h'][idx]=mean[field].to_numpy()
                added[f'{field}_departure_{hours}h'][idx]=(values[field]-mean[field]).to_numpy()
                added[f'{field}_coverage_{hours}h'][idx]=count[field].to_numpy()/(hours*6)
    return pd.concat([result,pd.DataFrame(added)],axis=1)


def main():
    config=ROOT/'config/weather_thermodynamics_20261101.json';plan=read(config);out=ROOT/plan['output'];old=ROOT/plan['baseline']
    if (out/'independent_verification.json').exists():raise FileExistsError('Preserve audit')
    summary=read(out/'summary.json');recorded=read(out/'plan.json')
    for name,digest in recorded['signatures'].items():assert sha(ROOT/name)==digest,name
    for name,digest in summary['files'].items():assert sha(out/name)==digest,name
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    assert not set(f.station)&set(plan['blocked_stations'])
    independent=independent_physical(f)
    actual=pd.read_parquet(out/'features.parquet',columns=list(independent))
    np.testing.assert_allclose(actual.to_numpy(),independent.to_numpy(),atol=1e-7,rtol=1e-10,equal_nan=True)
    feature_values=actual.size;maxdiff=float(np.nanmax(np.abs(actual.to_numpy()-independent.to_numpy())))
    del actual,independent;gc.collect();pa.default_memory_pool().release_unused()
    prefix_values=0
    for station in ['12207','23205','33205','33207']:
        for year in [2024,2025]:
            day=pd.Timestamp(year,12,15)
            q=f.loc[f.station.eq(station)&f.time.ge(day-pd.Timedelta(days=1))&f.time.lt(day+pd.Timedelta(days=1))]
            x=thermodynamic_features(q.reset_index(drop=True));keep=q.time.ge(day).to_numpy()
            full=pd.read_parquet(out/'features.parquet').loc[q.index[keep]].reset_index(drop=True)
            pd.testing.assert_frame_equal(x.loc[keep].reset_index(drop=True),full,check_exact=True)
            prefix_values+=full.size;del x,full;gc.collect();pa.default_memory_pool().release_unused()
    field=f.relative_humidity.to_numpy();asos=f.asos_humidity.where((f.asos_age_minutes>0)&(f.asos_age_minutes<=60)).to_numpy()
    aws=f.aws_humidity.where((f.aws_age_minutes>0)&(f.aws_age_minutes<=15)).to_numpy();nearest=np.where(np.isfinite(aws),aws,asos)
    good=np.isfinite(field)&np.isfinite(asos)&np.isfinite(nearest)
    replayed=0;refits=0;metric_checks=0
    for mode in ['joint','spatial']:
        output=pd.read_parquet(out/mode/'predictions.parquet')
        baseline=pd.read_parquet(old/mode/'predictions.parquet')
        pd.testing.assert_frame_equal(output[['station','time','observed','stable_history']],baseline[['station','time','observed','stable_history']],check_exact=True)
        for kind in plan['candidates']:
            measure=report(output,kind);metric_checks+=compare(measure,summary['reports'][mode]['candidates'][kind]['metrics'])
            metric_checks+=compare(bootstrap(output,kind,'stable_history',plan['bootstrap']),summary['reports'][mode]['candidates'][kind]['bootstrap'])
        for record in [r for r in summary['fits'] if r['mode']==mode]:
            kind=record['kind'];held=record['held'];year=record['query_winter']
            train=good&f.group.ne(held);query=good&f.group.eq(held)
            if year is not None:train&=f.winter.ne(year);query&=f.winter.eq(year)
            assert int(train.sum())==record['training_rows'] and int(query.sum())==record['query_rows']
            assert sorted(f.loc[train,'station'].unique())==record['training_stations']
            assert not set(record['training_stations'])&set(record['query_stations'])
            if year is not None:assert year not in record['training_winters']
            stem=held+('_'+str(year) if year is not None else '')+'__'+kind
            path=out/mode/(stem+'.joblib');model=joblib.load(path)
            x=pd.read_parquet(out/'features.parquet');qx=x.loc[query]
            assert list(x)==record['features']
            def inverse(score):
                if kind=='thermo_residual':return np.clip(score+nearest[query],0,100)
                b=np.clip(nearest[query]/100,.005,.995)
                return 100*expit(score+np.log(b/(1-b)))
            with deny_network() as attempts,threadpool_limits(limits=2):values=inverse(model.predict(qx))
            assert not attempts
            # 별도 logit 항등식의 반올림 한계를 확인하고 원 역함수의 비트 일치도 검사한다.
            expected=np.load(path.with_suffix('.npy'),allow_pickle=False)
            np.testing.assert_allclose(values,expected,atol=3e-14,rtol=1e-15)
            from src.weather_thermodynamics import inverse_target
            with threadpool_limits(limits=2):np.testing.assert_array_equal(inverse_target(model.predict(qx),nearest[query],kind),expected)
            key=pd.MultiIndex.from_frame(f.loc[query,['station','time']]);saved=output.set_index(['station','time']).loc[key,kind].to_numpy()
            np.testing.assert_array_equal(saved,expected);replayed+=len(values)
            # 두 출력·두 제외 조건에서 대표 하나씩 원 설정으로 재학습한다.
            representative=(held=='honam_baekyang' and (year is None or year==2024))
            if representative:
                train_y=field[train];base=nearest[train]
                if kind=='thermo_residual':target=train_y-base;jacobian=1.
                else:
                    y=np.clip(train_y/100,.005,.995);b=np.clip(base/100,.005,.995)
                    # 원 훈련과 같은 scipy logit을 사용해 입력 비트를 보존한다.
                    from scipy.special import logit
                    target=logit(y)-logit(b);jacobian=y*(1-y)
                count=f.loc[train].groupby(['station','winter']).station.transform('size').to_numpy(float)
                w=1/count;w/=w.mean();w=w*jacobian
                if kind=='thermo_logit':w/=w.mean()
                refit=HistGradientBoostingRegressor(**plan['model'])
                with deny_network() as attempts,threadpool_limits(limits=2):
                    refit.fit(x.loc[train],target,sample_weight=w)
                    np.testing.assert_array_equal(refit.predict(qx),model.predict(qx))
                assert not attempts;refits+=1;del refit
                print('REFIT',mode,kind,flush=True)
            del x,qx,model;gc.collect();pa.default_memory_pool().release_unused()
    # 게이트는 저장 지표가 아니라 다시 계산한 수치로 확인한다.
    accepted=[]
    for kind in plan['candidates']:
        passes=[]
        for mode in ['joint','spatial']:
            p=pd.read_parquet(out/mode/'predictions.parquet');a=report(p,kind);b=report(p,'stable_history');boot=bootstrap(p,kind,'stable_history',plan['bootstrap']);g=plan['gates']
            gates=dict(pooled=a['pooled']['mae']/b['pooled']['mae']<=1-g['minimum_mae_reduction'],
                both_winters=all(a['winters'][y]['mae']<=v['mae'] for y,v in b['winters'].items()),
                every_region=all(a['regions'][r]['mae']<=v['mae']*g['maximum_region_mae_ratio'] for r,v in b['regions'].items()),
                cold=a['cold']['mae']<=b['cold']['mae'],date_sensitivity=boot['quantiles'][2]<0)
            assert gates==summary['reports'][mode]['candidates'][kind]['gates'];passes.append(all(gates.values()))
        if all(passes):accepted.append(kind)
    assert accepted==summary['accepted_candidates'] and refits==4 and verify_preserved()==summary['preservation']
    write(out/'independent_verification.json',dict(status='passed',summary_sha256=sha(out/'summary.json'),
        independent_physical_feature_values=feature_values,maximum_feature_difference=maxdiff,prefix_bit_exact_feature_values=prefix_values,
        prediction_values=replayed,metric_checks=metric_checks,exact_refits=refits,accepted_candidates=accepted,audit_sha256=sha(Path(__file__))))
    print('THERMO VERIFIED',feature_values,replayed,metric_checks,refits,flush=True)


if __name__=='__main__':main()
