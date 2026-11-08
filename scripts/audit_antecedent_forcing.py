"""누적 입력을 10분 격자 필터로 재계산하고 모델·선택·지표를 별도로 검산한다."""
from pathlib import Path
import gc
import sys
import numpy as np
import pandas as pd
import torch
from scipy.signal import lfilter
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved
from scripts.audit_objective_icing import independent_features,independent_weights,choose_independent,same
from scripts.audit_icing_transition import independent_metrics,independent_events
from src.antecedent_forcing import fit_forcing
from src.objective_icing import group_data
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network

ADDED=['aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint','aws_age_minutes',
    'era5_temperature_2m','era5_soil_temperature_0_to_7cm','era5_soil_temperature_7_to_28cm',
    'era5_snow_depth','era5_soil_moisture_0_to_7cm']


def reference_frost(t,h):
    t=np.asarray(t,float);h=np.asarray(h,float);out=np.full(len(t),np.nan)
    valid=np.isfinite(t)&np.isfinite(h)&(h>0)&(h<=100)&(t>-100)&(t<100)
    log_pressure=np.log(h[valid]*.01)+17.62*t[valid]/(243.12+t[valid])
    out[valid]=np.divide(272.62, np.divide(22.46,log_pressure,out=np.full_like(log_pressure,np.inf),where=log_pressure!=0)-1)
    return out


def reference_history(times,temp,frost):
    """누락 시각을 0입력으로 채운 선형 필터. 생산 코드의 상태 재귀를 호출하지 않는다."""
    ticks=(times.to_numpy().astype('datetime64[ns]').astype(np.int64)//600_000_000_000)
    assert np.all(times.to_numpy().astype('datetime64[ns]').astype(np.int64)%600_000_000_000==0)
    indices=ticks-ticks[0];size=int(indices[-1]+1)
    contiguous=np.r_[False,np.diff(indices)==1];good=np.isfinite(temp)
    changes=np.zeros(len(temp));age=np.zeros(len(temp));sign=0
    for i,value in enumerate(temp):
        if not contiguous[i]:sign=0
        if not good[i]:sign=0;continue
        if contiguous[i] and i>0 and good[i-1]:age[i]=age[i-1]+10
        s=int(np.sign(value))
        if s:
            changes[i]=int(contiguous[i] and sign!=0 and s!=sign)
            sign=s if contiguous[i] or i==0 else 0
    output={}
    for tau in [30,360]:
        decay=np.exp(-10/tau)
        values=[np.where(good&contiguous,np.maximum(-temp,0)*(1-decay),0),
            np.where(good&contiguous&np.isfinite(frost),np.maximum(frost-temp,0)*(1-decay),0),changes]
        for name,value in zip(['cold','deposition','freeze_thaw'],values):
            impulse=np.zeros(size);impulse[indices]=value
            accumulated=lfilter([1.],[1.,-decay],impulse)[indices]
            accumulated[~good]=np.nan
            if name=='deposition':accumulated[~np.isfinite(frost)]=np.nan
            output[f'{name}_{tau}m']=accumulated
    history=np.minimum(age,360)/360;history[~good]=np.nan
    grid=np.full(size+6,np.nan);grid[indices+6]=temp
    output['history_fraction6h']=history;output['change1h']=temp-grid[indices]
    return output


def reference_features(f):
    x=independent_features(f)
    for name in ADDED[:5]:x[name]=f[name].where((f.aws_age_minutes>0)&(f.aws_age_minutes<=15))
    x['aws_source_age_minutes']=f.aws_age_minutes
    asos=reference_frost(f.asos_air_temp,f.asos_humidity);aws=reference_frost(x.aws_air_temp,x.aws_humidity)
    x['asos_frost_point']=asos;x['aws_frost_point']=aws
    x['asos_ground_frost_margin']=f.asos_ground_temp-asos
    x['aws_air_frost_margin']=x.aws_air_temp-aws;x['aws_asos_air_contrast']=x.aws_air_temp-f.asos_air_temp
    for depth in ['0_to_7cm','7_to_28cm']:
        x['era5_soil_air_contrast_'+depth]=f['era5_soil_temperature_'+depth]-f.era5_temperature_2m
    x['era5_snow_depth']=f.era5_snow_depth;x['era5_soil_moisture_0_to_7cm']=f.era5_soil_moisture_0_to_7cm
    instant=list(x)
    for source,temp,frost in [('asos_air',f.asos_air_temp.to_numpy(),asos),
        ('asos_ground',f.asos_ground_temp.to_numpy(),asos),('aws_air',x.aws_air_temp.to_numpy(),aws)]:
        names=[f'{source}_{name}_{tau}m' for tau in [30,360] for name in ['cold','deposition','freeze_thaw']]
        names += [source+'_history_fraction6h',source+'_change1h']
        for name in names:x[name]=np.nan
        for _,part in f.groupby(['station','winter']):
            ix=part.index.to_numpy();values=reference_history(part.time,temp[ix],frost[ix])
            for name,value in values.items():x.loc[ix,source+'_'+name]=value
    return x,instant


def replay(x,model):
    a=x.to_numpy(float);missing=np.isnan(a)
    z=np.concatenate([np.clip((np.where(missing,model['medians'],a)-model['means'])/model['scales'],-8,8),missing.astype(float)],axis=1)
    z=z.astype(np.float32).astype(float)
    return float(model['cap'])*np.tanh(z@model['coefficient'].astype(float)+float(model['intercept']))


def main():
    study=ROOT/'outputs/private/antecedent_forcing_20261031_v2';target=study/'independent_verification.json'
    if target.exists():raise FileExistsError('Preserve completed audit')
    plan=read(study/'plan.json');settings=plan['settings'];summary=read(study/'summary.json')
    for name,digest in plan['signatures'].items():assert sha(ROOT/name)==digest,name
    for name,digest in summary['files'].items():assert sha(study/name)==digest,name
    assert verify_preserved()==plan['preservation']
    f=pd.read_parquet(ROOT/settings['source']).sort_values(['station','time']).reset_index(drop=True)
    extra=pd.read_parquet(ROOT/settings['local_source'],columns=['station','time','ice',*ADDED]).sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(f[['station','time','ice']],extra[['station','time','ice']],check_exact=True)
    assert not set(f.station)&set(settings['blocked_stations']) and f.station.nunique()==23
    for c in ADDED:f[c]=extra[c]
    del extra;gc.collect()
    x,instant=reference_features(f);saved=pd.read_parquet(study/'features.parquet')
    assert list(x)==list(saved) and instant==read(study/'feature_receipt.json')['instantaneous_columns']
    np.testing.assert_allclose(x.to_numpy(),saved.to_numpy(),rtol=0,atol=1e-10,equal_nan=True)
    feature_error=float(np.nanmax(np.abs(x.to_numpy()-saved.to_numpy())))
    feature_count=saved.size
    del x;gc.collect()
    print('AUDIT FEATURES',saved.size,'values',feature_error,flush=True)
    torch.set_num_threads(settings['threads']);torch.use_deterministic_algorithms(True)
    groups=sorted(set(f.group)-{'competition'});cache={};current=None;refits=values_checked=0;maximum=0.
    for receipt in summary['fits']:
        key=tuple(receipt['excluded']);stem='__'.join(key)
        if key!=current:
            train=f.loc[~f.group.isin(key)&f.available&f.ice.isin([0,1])];query=f.loc[f.group.isin(key)]
            weights=independent_weights(train)
            np.testing.assert_allclose(weights,group_data(train)['row_weights'],rtol=0,atol=1e-12)
            cache[key]=pd.read_parquet(study/(stem+'__scores.parquet'));current=key
        scores=cache[key];columns=instant if receipt['kind']=='instantaneous' else list(saved)
        assert len(train)==receipt['train_rows'] and int(train.ice.sum())==receipt['train_positive_rows']
        assert sorted(train.station.unique())==receipt['train_stations'] and not set(train.station)&set(query.station)
        pd.testing.assert_frame_equal(query[scores.columns[:7]].reset_index(drop=True),scores.iloc[:,:7],check_exact=True)
        path=study/receipt['model'];assert sha(path)==receipt['sha256']
        with np.load(path,allow_pickle=False) as archive:model=dict(archive)
        assert columns==receipt['features']==list(model['feature_names'])
        a=saved.loc[train.index,columns];median=a.median().fillna(0).to_numpy();filled=a.fillna(dict(zip(a,median))).to_numpy()
        mean=filled.mean(axis=0);scale=filled.std(axis=0);scale[scale<1e-8]=1
        for name,value in [('medians',median),('means',mean),('scales',scale)]:np.testing.assert_allclose(model[name],value,rtol=0,atol=1e-12)
        with threadpool_limits(limits=2):prediction=replay(saved.loc[query.index,columns],model)
        actual=scores[receipt['kind']].to_numpy();maximum=max(maximum,float(np.max(np.abs(prediction-actual))))
        np.testing.assert_allclose(prediction,actual,rtol=0,atol=5e-6)
        for offset in settings['offsets_c']:
            mask=query.available.to_numpy();air=query.asos_air_temp.to_numpy()[mask]
            np.testing.assert_array_equal(air<=np.clip(prediction+offset,-2,2)[mask],air<=np.clip(actual+offset,-2,2)[mask])
        values_checked+=len(query)
        if key==(groups[0],):
            with deny_network() as attempts,threadpool_limits(limits=2):repeat=fit_forcing(train,saved.loc[train.index,columns],settings)
            assert not attempts
            for name in model:np.testing.assert_array_equal(repeat[name],model[name])
            refits+=1
        print('AUDIT MODEL',stem,receipt['kind'],flush=True)
        del a,filled,model;gc.collect()
    for receipt,key in zip(summary['reused'],cache):
        query=f.loc[f.group.isin(key)];path=ROOT/receipt['model'];assert sha(path)==receipt['sha256']
        with np.load(path,allow_pickle=False) as archive:model=dict(archive)
        with threadpool_limits(limits=2):p=replay(independent_features(query),model)
        np.testing.assert_allclose(p,cache[key].asos_bce,rtol=0,atol=5e-6)
        values_checked+=len(query)
    del saved,f,train,query;gc.collect()
    result=pd.read_parquet(study/'predictions.parquet');checks=choices=0
    for decision in summary['decisions']:
        held=decision['held'];table=pd.read_csv(study/(held+'__inner.csv'))
        inner=pd.concat([cache[tuple(sorted([held,g]))].loc[lambda q:q.group.eq(g)] for g in groups if g!=held],ignore_index=True)
        q=result.loc[result.group.eq(held)]
        assert not set(inner.station)&set(q.station)
        for r in table.to_dict('records'):
            delta=r['offset'] if pd.isna(r['model']) else np.clip(inner[r['model']]+r['offset'],-2,2)
            p=np.where(inner.available,inner.asos_air_temp.le(delta),np.nan);m=independent_metrics(inner,p)
            for key,column in [('f1_fixed_population','f1'),('precision_available_station_mean','precision'),
                ('recall_available_station_mean','recall'),('tp','tp'),('fp','fp'),('fn','fn')]:same(m[key],r[column]);checks+=1
            for year in [2024,2025]:
                mask=inner.winter.eq(year);same(independent_metrics(inner.loc[mask],p[mask])['f1_fixed_population'],r['f1_'+str(year)]);checks+=1
            outer_delta=r['offset'] if pd.isna(r['model']) else np.clip(q[r['model']]+r['offset'],-2,2)
            np.testing.assert_array_equal(q[r['candidate']],np.where(q.available,q.asos_air_temp.le(outer_delta),np.nan))
        for track,choice in decision['selected'].items():
            eligible=table.loc[table.model.ne('dose')] if track=='matched_instantaneous' else table
            assert choose_independent(eligible,'mean_f1' if track=='matched_instantaneous' else track)==choice
            np.testing.assert_array_equal(q[track],q[choice]);choices+=1
    for name,record in summary['reports'].items():
        for label,q in [('all',result),*[(str(y),result.loc[result.winter.eq(y)]) for y in [2024,2025]],
            *[(g,result.loc[result.group.eq(g)]) for g in groups]]:
            expected=record['all'] if label=='all' else record['winters'][label] if label.isdigit() else record['regions'][label]
            for key,value in independent_metrics(q,q[name]).items():same(value,expected[key]);checks+=1
        assert independent_events(result,result[name],result.asos_zero)==record['events']
    base_days=pd.read_csv(study/'asos_zero__daily.csv')
    for name in ['mean_f1','recall_guard','matched_instantaneous','asos_zero']:
        days=pd.read_csv(study/(name+'__daily.csv'));assert days[['station','date_kst']].equals(base_days[['station','date_kst']])
        means=[]
        for s in sorted(base_days.station.unique()):
            mask=base_days.station.eq(s)&base_days.f1.notna();means.append(float(days.loc[mask,'f1'].fillna(0).mean()) if mask.any() else 0.)
        same(float(np.mean(means)),summary['reports'][name]['baseline_calendar_f1'])
        if name not in summary['sensitivity']:continue
        starts=[np.random.default_rng(settings['seed']+i).integers(0,120,size=(2000,18)) for i in [0,1]]
        a=days.f1.to_numpy().reshape(-1,240);b=base_days.f1.to_numpy().reshape(-1,240);samples=[]
        for i in range(2000):
            indices=[]
            for season in [0,1]:indices.extend([int((start+j)%120+120*season) for start in starts[season][i] for j in range(7)][:120])
            means=[]
            for values in [a,b]:
                selected=values[:,indices];count=np.isfinite(selected).sum(axis=1)
                means.append(np.divide(np.nansum(selected,axis=1),count,out=np.zeros(len(count)),where=count>0).mean())
            samples.append(means[0]-means[1])
        expected=summary['sensitivity'][name]
        np.testing.assert_allclose(np.quantile(samples,[.025,.5,.975]),expected['difference_percentiles'],rtol=0,atol=1e-12)
        same(float(np.mean(np.asarray(samples)>0)),expected['fraction_positive'])
    base=summary['reports']['asos_zero'];p=summary['reports']['mean_f1'];m=summary['reports']['matched_instantaneous']
    gates=dict(f1_asos=p['all']['f1_fixed_population']>=1.01*base['all']['f1_fixed_population'],
        f1_matched=p['all']['f1_fixed_population']>=1.01*m['all']['f1_fixed_population'],
        precision=p['all']['precision_available_station_mean']>=base['all']['precision_available_station_mean'],
        recall=p['all']['recall_available_station_mean']>=base['all']['recall_available_station_mean'],
        winters=all(p['winters'][y]['f1_fixed_population']>=base['winters'][y]['f1_fixed_population'] for y in ['2024','2025']),
        regions=all(p['regions'][g]['f1_fixed_population']>=base['regions'][g]['f1_fixed_population'] for g in groups),
        stations=all(p['all']['station_f1_fixed'][s]>=base['all']['station_f1_fixed'][s] for s in base['all']['station_f1_fixed']),
        events=p['events']['lost_events']==0,fixed_calendar=p['baseline_calendar_f1']>=base['baseline_calendar_f1'])
    assert gates==summary['gates'] and all(gates.values())==summary['primary_success']
    assert verify_preserved()==plan['preservation']
    write(target,dict(status='passed',feature_values=feature_count,maximum_feature_difference=feature_error,
        model_files=len(summary['fits']),reused_models=len(summary['reused']),model_values=values_checked,
        maximum_numpy_torch_difference=maximum,deterministic_refits=refits,nested_choices=choices,
        metric_checks=checks,event_checks=len(summary['reports']),gate_checks=len(gates),fixed_calendar_checks=4,
        block_resampling_checks=4000,summary_sha256=sha(study/'summary.json'),audit_script_sha256=sha(Path(__file__)),
        preservation=plan['preservation'],protected_outcomes_read=False,new_four_site_outcomes_read=False))
    print('AUDIT COMPLETE',values_checked,'scores',checks,'metrics',flush=True)


if __name__=='__main__':main()
