"""새 ASOS 입력·날짜 균형·형태 제한 50개 모델과 수분 지속 6정책을 중첩 공간 비교한다."""
import argparse,json,time
from datetime import datetime,timezone
from itertools import combinations
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.synoptic_icing import feature_table,fixed_policies,sample_weights,MONOTONE
from src.two_winter import validate,curve
from src.runtime_metrics import runtime_daily
from src.extended_comparison import event_retention
from src.offline_runtime import deny_network
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation
from scripts.evaluate_thermal_classification import available,choose

CONFIG=ROOT/'config/icing_synoptic_20261025.json'
KEYS=['station','time','winter','group','ice','asos_air_temp']
def read(p):return json.loads(p.read_text('utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')

def assert_matching_keys(saved,expected):
    # Parquet의 index=False 저장·복원 전후에도 실제 행키와 순서는 같아야 한다.
    pd.testing.assert_frame_equal(saved[['station','time']].reset_index(drop=True),
                                  expected[['station','time']].reset_index(drop=True))

def report_predictions(f,out):
    names=[n for n in f if n not in [*KEYS,'available']];reports={};stations=[];days=[];regions=[]
    for name in names:
        reports[name]={}
        for year in ['all',2024,2025]:
            part=f if year=='all' else f.loc[f.winter.eq(year)]
            r,st,d=runtime_daily(part,part[name]);reports[name][str(year)]=r
            if year=='all':stations.append(st.assign(method=name));days.append(d.assign(method=name))
        r,events=event_retention(f,f[name],f.current);reports[name]['events']=r;events.to_csv(out/(name+'_events.csv'),index=False)
        for group,part in f.groupby('group'):
            r,_,_=runtime_daily(part,part[name]);regions.append(dict(method=name,group=group,**r))
    st=pd.concat(stations,ignore_index=True);oldst=st.loc[st.method.eq('current')].set_index('station').f1.fillna(0)
    old=reports['current']['all']
    for name,r in reports.items():
        s=st.loc[st.method.eq(name)].set_index('station').f1.fillna(0);n=r['all']
        gates=dict(f1_improves=n['f1_fixed_population']>=old['f1_fixed_population']*1.01,
            precision_noninferior=n['precision_available_station_mean'] is not None and n['precision_available_station_mean']>=old['precision_available_station_mean'],
            recall_noninferior=n['recall_available_station_mean'] is not None and n['recall_available_station_mean']>=old['recall_available_station_mean'],
            each_winter=all(r[str(y)]['f1_fixed_population']>=reports['current'][str(y)]['f1_fixed_population'] for y in [2024,2025]),
            each_station=bool(s.ge(oldst).all()),events_preserved=r['events']['lost_events']==0,
            beats_asos=n['f1_fixed_population']>reports['asos_zero']['all']['f1_fixed_population'])
        r['gates']=gates;r['eligible']=all(gates.values())
        print(name,round(n['f1_fixed_population'],8),'eligible',r['eligible'],flush=True)
    st.to_csv(out/'stations.csv',index=False);pd.concat(days,ignore_index=True).to_csv(out/'daily.csv',index=False)
    pd.DataFrame(regions).to_csv(out/'regions.csv',index=False);f.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    return reports

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();plan=read(CONFIG)
    if not out.is_relative_to((ROOT/'outputs/private').resolve()):raise ValueError('Private output required')
    paths=[CONFIG,Path(__file__),ROOT/'src/synoptic_icing.py',ROOT/'src/two_winter.py',ROOT/'src/runtime_metrics.py',ROOT/'src/extended_comparison.py',ROOT/plan['data'],ROOT/plan['baseline']]
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    if out.exists():
        assert read(out/'plan.json')['signatures']==signatures
        if (out/'summary.json').exists():raise FileExistsError('Preserve completed research')
    else:out.mkdir(parents=True);write(out/'plan.json',dict(settings=plan,signatures=signatures,started_at_utc=datetime.now(timezone.utc).isoformat()))
    frozen=preservation();data=validate(pd.read_parquet(ROOT/plan['data'])).sort_values(['station','time']).reset_index(drop=True)
    assert sha(ROOT/plan['data'])==read((ROOT/plan['data']).parent/'receipt.json')['data_sha256']
    base=validate(pd.read_parquet(ROOT/plan['baseline'])).sort_values(['station','time']).reset_index(drop=True)
    assert sha(ROOT/plan['baseline'])==read((ROOT/plan['baseline']).parent/'audit_runtime.json')['runtime_prediction_sha256']
    groups=sorted(set(data.group)-{'competition'});assert len(groups)==4
    contexts=[*((g,) for g in groups),*combinations(groups,2)];valid=available(data);matrices={k:feature_table(data,k) for k in ['base','extra']}
    fixed=fixed_policies(data);names=[c['name'] for c in plan['candidates']];stores={};fits=[]
    for spec in plan['candidates']:
        folder=out/spec['name'];folder.mkdir(exist_ok=True);x=matrices[spec['features']];stores[spec['name']]={}
        for key in contexts:
            stem='__'.join(key);receipt_path=folder/(stem+'.json');predpath=folder/(stem+'.parquet');modelpath=folder/(stem+'.joblib')
            qmask=data.group.isin(key);tmask=~qmask&valid&data.ice.isin([0,1]);train=data.loc[tmask];query=data.loc[qmask]
            assert not set(train.station)&set(query.station)
            if receipt_path.exists():
                receipt=read(receipt_path);assert sha(modelpath)==receipt['model_sha256'] and sha(predpath)==receipt['prediction_sha256']
                pred=pd.read_parquet(predpath)
            else:
                params=dict(plan['parameters'],interaction_cst=spec['interactions'])
                if spec['monotone']:params['monotonic_cst']={n:MONOTONE.get(n,0) for n in x}
                model=HistGradientBoostingClassifier(**params);started=time.perf_counter();w=sample_weights(train,spec['weights'])
                with deny_network() as attempts,threadpool_limits(limits=plan['threads']):
                    model.fit(x.loc[tmask],train.ice.to_numpy(int),sample_weight=w)
                    scores=model.predict_proba(x.loc[qmask])[:,1]
                assert not attempts and np.isfinite(scores).all()
                pred=query[KEYS].copy();pred['available']=valid[qmask];pred['score']=scores
                joblib.dump(model,modelpath,compress=3);pred.to_parquet(predpath,index=False,compression='zstd')
                receipt=dict(candidate=spec['name'],excluded_groups=list(key),training_stations=sorted(train.station.unique()),
                    query_stations=sorted(query.station.unique()),training_rows=len(train),query_rows=len(query),features=list(x),parameters=params,
                    training_weight_sum=float(w.sum()),training_weight_min=float(w.min()),training_weight_max=float(w.max()),
                    weighted_positive_fraction=float(np.average(train.ice,weights=w)),model_sha256=sha(modelpath),prediction_sha256=sha(predpath),seconds=time.perf_counter()-started)
                write(receipt_path,receipt);print('FIT',spec['name'],stem,round(receipt['seconds'],1),flush=True)
            stores[spec['name']][key]=pred;fits.append(receipt);write(out/'progress.json',dict(models_complete=len(fits),planned_models=50))
    parts=[];decisions={};allnames=[*names,*fixed,'asos_zero']
    for outer in groups:
        tables=[]
        for name in allnames:
            is_model=name in names
            if is_model:
                inner=pd.concat([stores[name][tuple(sorted([outer,h]))].loc[lambda x:x.group.eq(h)] for h in groups if h!=outer]).copy()
                scores=inner.score.to_numpy()
            else:
                mask=data.group.isin([g for g in groups if g!=outer]);inner=data.loc[mask,KEYS].copy();inner['available']=valid[mask]
                scores=data.loc[mask,'asos_air_temp'].le(0).to_numpy(float) if name=='asos_zero' else fixed[name][mask]
            inner.loc[~inner.available,'ice']=np.nan
            thresholds={} if is_model else dict(thresholds=np.array([.5]))
            tab=curve(inner,scores,**thresholds);tab['mean_f1']=tab.f1_fixed_population
            tab['worst_winter_f1']=np.minimum(*[curve(inner.loc[inner.winter.eq(y)],scores[inner.winter.eq(y)],**thresholds).f1_fixed_population.to_numpy() for y in [2024,2025]])
            tab['candidate']=name;tables.append(tab)
        table=pd.concat(tables,ignore_index=True);table.to_csv(out/(outer+'_selection.csv'),index=False)
        mask=data.group.eq(outer);part=data.loc[mask,KEYS].copy();part['available']=valid[mask]
        for name,score in fixed.items():part[name]=np.where(part.available,score[mask],np.nan)
        part['asos_zero']=np.where(part.available,part.asos_air_temp.le(0),np.nan)
        decisions[outer]={}
        for track in plan['selection_tracks']:
            for name in [*names,'selected']:
                choice=choose(table if name=='selected' else table.loc[table.candidate.eq(name)],track);chosen=choice['candidate']
                if chosen in names:
                    q=stores[chosen][(outer,)];assert_matching_keys(q,part);score=q.score.to_numpy()
                else:score=part.asos_air_temp.le(0).to_numpy(float) if chosen=='asos_zero' else fixed[chosen][mask]
                col=name+'_'+track;part[col]=np.where(part.available,score>=choice['threshold'],np.nan);decisions[outer][col]=choice
        parts.append(part);print('SELECTED',outer,decisions[outer]['selected_mean_f1']['candidate'],flush=True)
    f=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(f[['station','time','ice']],base[['station','time','ice']]);np.testing.assert_array_equal(f.available,base.physical_both.notna())
    f['current']=base.physical_both.to_numpy();reports=report_predictions(f,out)
    write(out/'decisions.json',decisions);write(out/'fit_receipts.json',fits);assert preservation()==frozen
    write(out/'summary.json',dict(status='synoptic_icing_comparison_complete',model_fits=len(fits),rows=len(f),reports=reports,
        source_signatures=signatures,protected_labels_read=False,new_independent_assessment=False,production_model_changed=False,
        frozen_counts=list(frozen),files={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='summary.json'}))

if __name__=='__main__':main()
