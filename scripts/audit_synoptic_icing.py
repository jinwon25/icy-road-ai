"""새 기상 이력·학습 가중치·저장 모델·중첩 선택·지표를 별도 계산으로 대조한다."""
import argparse
from collections import Counter
from itertools import combinations
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.synoptic_icing import feature_table,wetness_memory,fixed_policies,sample_weights,MONOTONE
from src.two_winter import validate
from src.data_source import sha256_file as sha
from scripts.evaluate_synoptic_icing import read,write,KEYS
from scripts.evaluate_thermal_classification import available
from scripts.audit_icing_transition import independent_metrics,independent_events
from scripts.evaluate_method_blending import preservation


def independent_memory(f):
    n=len(f);t=f.time.to_numpy(dtype='datetime64[ns]').view('int64');state={};result=np.full((n,3),np.nan)
    a=f.asos_air_temp.to_numpy(float);g=f.asos_ground_temp.to_numpy(float);d=f.asos_dewpoint_obs.to_numpy(float)
    h=f.asos_humidity.to_numpy(float);r=f.asos_rain_mm.to_numpy(float);s=f.asos_snow_cm.to_numpy(float);age=f.asos_age_minutes.to_numpy(float)
    for i,station in enumerate(f.station):
        known=np.isfinite(a[i]) and 0<age[i]<=60 and any(np.isfinite(v) for v in [h[i],r[i],s[i]])
        if not known:state.pop(station,None);continue
        previous,wet_at=state.get(station,(None,None))
        if previous is None or t[i]-previous!=600_000_000_000 or a[i]>2:wet_at=None
        wet=r[i]>0 or s[i]>0 or (h[i]>=90 and g[i]<=d[i])
        if wet and a[i]<=2:wet_at=t[i]
        elapsed=np.inf if wet_at is None else (t[i]-wet_at)/3_600_000_000_000
        result[i]=[int(wet),int(elapsed<=24),int(elapsed<=72)];state[station]=(t[i],wet_at)
    return result


def independent_weights(f):
    keys=list(zip(f.station,f.winter,f.time.dt.date,f.ice));counts=Counter(keys)
    labels={};days={}
    for station,winter,day,label in counts:
        labels.setdefault((station,winter,day),set()).add(label)
        days.setdefault((station,winter),set()).add(day)
    w=np.array([1/(counts[k]*len(labels[k[:3]])*len(days[k[:2]])) for k in keys])
    return w/w.mean()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--study',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();study=args.study.resolve();out=args.output.resolve()
    if out.exists() or not out.is_relative_to((ROOT/'outputs/private').resolve()):raise ValueError('New private output required')
    summary=read(study/'summary.json');plan=read(study/'plan.json')['settings'];frozen=preservation()
    for name,digest in summary['source_signatures'].items():assert sha(ROOT/name)==digest,name
    for name,digest in summary['files'].items():assert sha(study/name)==digest,name
    data=validate(pd.read_parquet(ROOT/plan['data'])).sort_values(['station','time']).reset_index(drop=True)
    f=pd.read_parquet(study/'predictions.parquet');out.mkdir(parents=True)
    inputs=['station','time','asos_air_temp','asos_ground_temp','asos_dewpoint_obs','asos_humidity','asos_rain_mm','asos_snow_cm','asos_age_minutes']
    manual=independent_memory(data);np.testing.assert_allclose(manual,wetness_memory(data[inputs]),atol=0,rtol=0,equal_nan=True)
    fixed=fixed_policies(data)
    for kind,column in [('air','asos_air_temp'),('ground','asos_ground_temp')]:
        for j,hours in enumerate([0,24,72]):
            known=data[column].notna().to_numpy()&np.isfinite(manual[:,j])
            actual=np.where(known,(data[column].to_numpy()<=0)&(manual[:,j]>0),data.asos_air_temp.le(0).to_numpy()).astype(float)
            np.testing.assert_array_equal(actual,fixed[f'{kind}_wet_{hours}h'])
    groups=sorted(set(data.group)-{'competition'});contexts=[*((g,) for g in groups),*combinations(groups,2)]
    matrices={k:feature_table(data,k) for k in ['base','extra']};valid=available(data);replays=0;weight_checks=0;monotone_checks=0
    for spec in plan['candidates']:
        x=matrices[spec['features']]
        for key in contexts:
            stem='__'.join(key);record=read(study/spec['name']/(stem+'.json'));modelpath=study/spec['name']/(stem+'.joblib');predpath=study/spec['name']/(stem+'.parquet')
            assert sha(modelpath)==record['model_sha256'] and sha(predpath)==record['prediction_sha256']
            qmask=data.group.isin(key);tmask=~qmask&valid&data.ice.isin([0,1]);train=data.loc[tmask]
            assert sorted(train.station.unique())==record['training_stations'] and not set(train.station)&set(data.loc[qmask,'station'])
            assert set(train.winter)=={2024,2025}
            w=independent_weights(train) if spec['weights']=='day' else np.ones(len(train))
            np.testing.assert_allclose(w,sample_weights(train,spec['weights']),rtol=1e-14,atol=1e-14)
            np.testing.assert_allclose([w.sum(),w.min(),w.max(),np.average(train.ice,weights=w)],
                [record['training_weight_sum'],record['training_weight_min'],record['training_weight_max'],record['weighted_positive_fraction']],rtol=1e-14,atol=1e-12)
            weight_checks+=1;model=joblib.load(modelpath);q=pd.read_parquet(predpath)
            pd.testing.assert_frame_equal(q[KEYS].reset_index(drop=True),data.loc[qmask,KEYS].reset_index(drop=True))
            with threadpool_limits(limits=2):
                scores=model.predict_proba(x.loc[qmask])[:,1];np.testing.assert_array_equal(scores,q.score)
                if spec['monotone']:
                    probe=x.loc[qmask].iloc[:64].copy();reference=model.predict_proba(probe)[:,1]
                    for col,sign in MONOTONE.items():
                        if col not in probe or not probe[col].notna().any():continue
                        changed=probe.copy();changed[col]+=1.;difference=model.predict_proba(changed)[:,1]-reference
                        assert (sign*difference>=-1e-12).all(),(spec['name'],col)
                        monotone_checks+=1
            replays+=1;write(out/'progress.json',dict(models_replayed=replays,planned_models=50))
    checks=0
    for name,report in summary['reports'].items():
        for year in ['all',2024,2025]:
            part=f if year=='all' else f.loc[f.winter.eq(year)];r=independent_metrics(part,part[name])
            for metric in ['f1_fixed_population','precision_available_station_mean','recall_available_station_mean']:
                expected=report[str(year)][metric]
                if expected is None:assert r[metric] is None
                else:np.testing.assert_allclose(r[metric],expected,atol=1e-12,rtol=0)
            checks+=1
        assert independent_events(f,f[name],f.current)==report['events']
    decisions=read(study/'decisions.json');names=[s['name'] for s in plan['candidates']];selections=0
    for outer,choices in decisions.items():
        table=pd.read_csv(study/(outer+'_selection.csv'),float_precision='round_trip')
        for method,choice in choices.items():
            track='worst_winter_f1' if method.endswith('worst_winter_f1') else 'mean_f1'
            allowed_table=table if method.startswith('selected_') else table.loc[table.candidate.eq(method.removesuffix('_'+track))]
            winner=min(allowed_table.to_dict('records'),key=lambda r:(-r[track],r['fp'],-r['threshold'],r['candidate']))
            assert (winner['candidate'],winner['threshold'])==(choice['candidate'],choice['threshold'])
            name=choice['candidate'];chunks=[]
            for held in groups:
                if held==outer:continue
                if name in names:
                    q=pd.read_parquet(study/name/('__'.join(sorted([outer,held]))+'.parquet'));q=q.loc[q.group.eq(held)].copy();score=q.score.to_numpy()
                else:
                    mask=data.group.eq(held);q=data.loc[mask,KEYS].copy();q['available']=valid[mask]
                    score=q.asos_air_temp.le(0).to_numpy(float) if name=='asos_zero' else fixed[name][mask]
                q['p']=np.where(q.available,score>=choice['threshold'],np.nan);chunks.append(q)
            inner=pd.concat(chunks,ignore_index=True);assert not set(inner.station)&set(f.loc[f.group.eq(outer),'station'])
            actual=independent_metrics(inner,inner.p);assert actual['fp']==choice['fp']
            np.testing.assert_allclose(actual['f1_fixed_population'],choice['mean_f1'],atol=1e-12,rtol=0)
            worst=min(independent_metrics(inner.loc[inner.winter.eq(y)],inner.loc[inner.winter.eq(y),'p'])['f1_fixed_population'] for y in [2024,2025])
            np.testing.assert_allclose(worst,choice['worst_winter_f1'],atol=1e-12,rtol=0)
            if name in names:
                q=pd.read_parquet(study/name/(outer+'.parquet'));score=q.score.to_numpy();availability=q.available.to_numpy()
            else:
                mask=data.group.eq(outer);score=data.loc[mask,'asos_air_temp'].le(0).to_numpy(float) if name=='asos_zero' else fixed[name][mask];availability=valid[mask]
            np.testing.assert_array_equal(np.where(availability,score>=choice['threshold'],np.nan),f.loc[f.group.eq(outer),method])
            selections+=1
    # 원인 진단의 수치도 독립 혼동행렬·사건 구현으로 확인한다.
    gap=read(ROOT/'outputs/private/icing_gap_diagnosis_20261025_v1/summary.json')
    base=validate(pd.read_parquet(ROOT/plan['baseline'])).sort_values(['station','time']).reset_index(drop=True)
    for name in ['current','asos_zero']:
        r=independent_metrics(f,f[name]);np.testing.assert_allclose(r['f1_fixed_population'],gap['reports'][name]['metrics']['f1_fixed_population'],atol=1e-12,rtol=0)
    air=base.asos_air_temp.to_numpy()<=0;cold=base.temperature_both.to_numpy()<=0
    water=(base.aws_dewpoint.to_numpy()>=base.temperature_both.to_numpy())|(base.rain15_max_3h.to_numpy()>0)|(base.asos_snow_cm.to_numpy()>0)
    masks={'air_only_temperature':air&~cold,'air_only_water':air&cold&~water,'both_alarm':air&cold&water,
           'current_only':~air&cold&water,'neither':~(air|(cold&water))}
    for name,mask in masks.items():
        y=base.loc[mask&base.ice.isin([0,1])&base.physical_both.notna(),'ice']
        assert dict(rows=len(y),positive=int(y.eq(1).sum()),negative=int(y.eq(0).sum()))==gap['disagreement_totals'][name]
    assert preservation()==frozen
    result=dict(status='synoptic_icing_independently_verified',models_replayed=replays,weight_checks=weight_checks,
        conditional_monotonicity_checks=monotone_checks,memory_values_checked=int(manual.size),metric_checks=checks,
        event_checks=len(summary['reports']),nested_selection_checks=selections,diagnostic_categories_checked=len(masks),
        summary_sha256=sha(study/'summary.json'),predictions_sha256=sha(study/'predictions.parquet'),
        diagnostic_sha256=sha(ROOT/'outputs/private/icing_gap_diagnosis_20261025_v1/summary.json'),
        audit_code_sha256=sha(Path(__file__)),protected_labels_read=False,frozen_counts=list(frozen))
    write(out/'receipt.json',result);print(result,flush=True)

if __name__=='__main__':main()
