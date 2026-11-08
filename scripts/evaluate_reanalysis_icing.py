"""같은 분류기·가중치에서 추가 지표면 입력만 비교하고 임계값은 내부 지역에서 선택한다."""
from datetime import datetime,timezone
from itertools import combinations
from pathlib import Path
import sys
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.anchored_icing import linear_features
from src.reanalysis_models import added_columns
from src.synoptic_icing import sample_weights
from src.exact_daily_threshold import select_exact_thresholds
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.fetch_reanalysis_inputs import read,write
from scripts.evaluate_objective_icing import verify_preserved,report,fixed_calendar_f1,block_sensitivity
from scripts.audit_icing_transition import independent_metrics


def choose(rows,track):
    best=max(r[track] for r in rows)
    tied=[r for r in rows if r[track]>=best-1e-12]
    return sorted(tied,key=lambda r:(r['complexity'],r['fp'],-r['threshold'],r['candidate']))[0]


def main():
    config=ROOT/'config/reanalysis_icing_20261031.json';plan=read(config);out=ROOT/plan['output']
    audit=read(ROOT/plan['input_audit']);assert audit['status']=='passed'
    assert sha(ROOT/plan['reanalysis_source'])==audit['data_sha256']
    sources=[config,Path(__file__),ROOT/plan['asos_source'],ROOT/plan['reanalysis_source'],ROOT/plan['input_audit'],
             ROOT/'src/exact_daily_threshold.py',ROOT/'src/anchored_icing.py',ROOT/'src/synoptic_icing.py',
             ROOT/'src/reanalysis_models.py',ROOT/'scripts/evaluate_objective_icing.py']
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in sources};frozen=verify_preserved()
    if out.exists():assert read(out/'plan.json')['signatures']==signatures
    else:
        out.mkdir(parents=True);write(out/'plan.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),settings=plan,
            signatures=signatures,preservation=frozen,retrospective_only=True,new_independent_assessment=False))
    if (out/'summary.json').exists():raise FileExistsError('Preserve completed study')
    f=pd.read_parquet(ROOT/plan['asos_source']).sort_values(['station','time']).reset_index(drop=True)
    extra=pd.read_parquet(ROOT/plan['reanalysis_source'],columns=['station','time','ice',*added_columns('era5_memory')]).sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(f[['station','time','ice']],extra[['station','time','ice']],check_exact=True)
    assert len(set(f.station))==23 and not set(f.station)&set(plan['blocked_stations'])
    xbase=linear_features(f);groups=sorted(set(f.group)-{'competition'});keys=[*((g,) for g in groups),*combinations(groups,2)]
    stores={};fits=[]
    for candidate in plan['candidates']:
        x=xbase if candidate=='asos15' else pd.concat([xbase,extra[added_columns(candidate)]],axis=1)
        folder=out/candidate;folder.mkdir(exist_ok=True);stores[candidate]={}
        for excluded in keys:
            stem='__'.join(excluded);modelpath=folder/(stem+'.joblib');predpath=folder/(stem+'.parquet');recordpath=folder/(stem+'.json')
            train=f.loc[~f.group.isin(excluded)&f.available&f.ice.isin([0,1])];query=f.loc[f.group.isin(excluded)]
            assert not set(train.station)&set(query.station)
            if recordpath.exists():
                record=read(recordpath);assert sha(modelpath)==record['model_sha256'] and sha(predpath)==record['predictions_sha256']
                score=pd.read_parquet(predpath)
            else:
                if modelpath.exists() or predpath.exists():raise FileExistsError('Unrecorded output; inspect before resuming')
                model=HistGradientBoostingClassifier(**plan['model']);started=time.perf_counter()
                with deny_network() as attempts,threadpool_limits(limits=plan['threads']):
                    model.fit(x.loc[train.index],train.ice.to_numpy(int),sample_weight=sample_weights(train,'day'))
                    values=model.predict_proba(x.loc[query.index])[:,1]
                assert not attempts and np.isfinite(values).all()
                score=query[['station','time','group','winter','ice','available','asos_air_temp']].copy();score['score']=values
                score.to_parquet(predpath,index=False,compression='zstd');joblib.dump(model,modelpath,compress=3)
                record=dict(candidate=candidate,excluded=list(excluded),training_stations=sorted(train.station.unique()),
                    training_rows=len(train),features=list(x),parameters=model.get_params(),seconds=time.perf_counter()-started,
                    model_sha256=sha(modelpath),predictions_sha256=sha(predpath))
                write(recordpath,record)
            stores[candidate][excluded]=score;fits.append(record)
            print('FIT',len(fits),'/30',candidate,stem,round(record['seconds'],1),flush=True)
    decisions=[];parts=[]
    for held in groups:
        tables={track:[] for track in ['mean_f1','worst_winter_f1']}
        q=stores['asos15'][(held,)][['station','time','group','winter','ice','available','asos_air_temp']].copy()
        q['asos_zero']=np.where(q.available,q.asos_air_temp.le(0),np.nan)
        for complexity,candidate in enumerate(plan['candidates'],start=1):
            inner=pd.concat([stores[candidate][tuple(sorted([held,h]))].loc[lambda r:r.group.eq(h)] for h in groups if h!=held],ignore_index=True)
            chosen=select_exact_thresholds(inner,np.where(inner.available,inner.score,np.nan))
            if candidate=='asos15':
                base=np.where(inner.available,inner.asos_air_temp.le(0),np.nan)
                metric=independent_metrics(inner,base)
                yearly=[independent_metrics(inner.loc[inner.winter.eq(y)],base[inner.winter.eq(y)])['f1_fixed_population'] for y in [2024,2025]]
                record=dict(candidate='asos_zero',complexity=0,threshold=.5,mean_f1=metric['f1_fixed_population'],
                            worst_winter_f1=min(yearly),fp=metric['fp'],tp=metric['tp'],fn=metric['fn'])
                for track in tables:tables[track].append(record.copy())
            for track,record in chosen.items():
                record.update(candidate=candidate,complexity=complexity)
                tables[track].append(record)
                q[candidate+'_'+track]=np.where(q.available,stores[candidate][(held,)].score.ge(record['threshold']),np.nan)
        choices={}
        for track,rows in tables.items():
            for label,eligible in [('selected_',rows),('baseline_',[r for r in rows if r['candidate'] in ['asos_zero','asos15']])]:
                selection=choose(eligible,track);choices[label+track]=selection
                column='asos_zero' if selection['candidate']=='asos_zero' else selection['candidate']+'_'+track
                q[label+track]=q[column]
        write(out/(held+'__inner_selection.json'),tables)
        decisions.append(dict(held=held,choices=choices));parts.append(q)
    write(out/'decisions.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),outer_metrics_computed=False,decisions=decisions))
    result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    result.to_parquet(out/'predictions.parquet',index=False,compression='zstd');reports={};days={}
    names=['asos_zero',*[c+'_'+t for c in plan['candidates'] for t in ['mean_f1','worst_winter_f1']],
           *[label+t for label in ['selected_','baseline_'] for t in ['mean_f1','worst_winter_f1']]]
    for name in names:
        reports[name],days[name],events=report(result,name,plan)
        reports[name]['baseline_calendar_f1']=fixed_calendar_f1(days[name],days['asos_zero'])
        days[name].to_csv(out/(name+'__daily.csv'),index=False);events.to_csv(out/(name+'__events.csv'),index=False)
        print('RESULT',name,reports[name]['all']['f1_fixed_population'],reports[name]['events'],flush=True)
    primary=reports[plan['primary_track']];base=reports['asos_zero'];matched=reports['baseline_mean_f1']
    gates=dict(f1_asos=primary['all']['f1_fixed_population']>=1.01*base['all']['f1_fixed_population'],
        f1_matched=primary['all']['f1_fixed_population']>=1.01*matched['all']['f1_fixed_population'],
        precision=primary['all']['precision_available_station_mean'] is not None and primary['all']['precision_available_station_mean']>=base['all']['precision_available_station_mean'],
        recall=primary['all']['recall_available_station_mean'] is not None and primary['all']['recall_available_station_mean']>=base['all']['recall_available_station_mean'],
        winters=all(primary['winters'][y]['f1_fixed_population']>=base['winters'][y]['f1_fixed_population'] for y in base['winters']),
        regions=all(primary['regions'][g]['f1_fixed_population']>=base['regions'][g]['f1_fixed_population'] for g in groups),
        stations=all(primary['all']['station_f1_fixed'][s]>=base['all']['station_f1_fixed'][s] for s in base['all']['station_f1_fixed']),
        events=primary['events']['lost_events']==0,fixed_calendar=primary['baseline_calendar_f1']>=base['baseline_calendar_f1'])
    sensitivity=block_sensitivity(days[plan['primary_track']],days['asos_zero'],plan['seed'])
    assert verify_preserved()==frozen
    write(out/'summary.json',dict(status='reanalysis_icing_complete',fits=fits,reports=reports,decisions=decisions,
        gates=gates,primary_success=all(gates.values()),sensitivity=sensitivity,preservation=frozen,
        retrospective_only=True,production_model_changed=False,new_independent_assessment=False,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))


if __name__=='__main__':main()
