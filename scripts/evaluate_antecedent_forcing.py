"""같은 제한 BCE에서 순간 기상과 감쇠 이력을 비교하며 외부 지역 정답으로 선택하지 않는다."""
from itertools import combinations
from pathlib import Path
import argparse
import gc
import shutil
import sys
import time
import numpy as np
import pandas as pd
import torch
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.antecedent_forcing import local_features, fit_forcing, correction_from_features
from src.objective_icing import correction, policies, predictions, choose
from src.additive_icing import metric_table
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.evaluate_objective_icing import read,write,now,verify_preserved,report,fixed_calendar_f1,block_sensitivity


ADDED=['aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint','aws_age_minutes',
       'era5_temperature_2m','era5_soil_temperature_0_to_7cm','era5_soil_temperature_7_to_28cm',
       'era5_snow_depth','era5_soil_moisture_0_to_7cm']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--max-new-fits',type=int);args=parser.parse_args()
    config=ROOT/'config/antecedent_forcing_20261031.json';plan=read(config);out=ROOT/plan['out'];control=ROOT/plan['control_study']
    local_audit=read(ROOT/plan['local_audit']);assert local_audit['status']=='passed'
    assert sha(ROOT/plan['local_source'])==local_audit['data_sha256']
    oldaudit=read(control/'independent_verification.json');assert oldaudit['status']=='passed'
    assert sha(control/'summary.json')==oldaudit['summary_sha256']
    paths=[config,Path(__file__),ROOT/plan['source'],ROOT/plan['local_source'],ROOT/plan['local_audit'],
        control/'summary.json',control/'independent_verification.json',ROOT/'src/antecedent_forcing.py',
        ROOT/'src/objective_icing.py',ROOT/'src/additive_icing.py',ROOT/'src/synoptic_icing.py',
        ROOT/'src/anchored_icing.py',ROOT/'scripts/evaluate_objective_icing.py']
    prior=ROOT/plan['feature_cache']
    paths.extend([prior/'plan.json',prior/'features.parquet',prior/'feature_receipt.json'])
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in paths};frozen=verify_preserved()
    if out.exists():assert read(out/'plan.json')['signatures']==signatures
    else:
        out.mkdir(parents=True);write(out/'plan.json',dict(at_utc=now(),settings=plan,signatures=signatures,
            preservation=frozen,outer_metrics_computed=False))
    if (out/'summary.json').exists():raise FileExistsError('Preserve completed study')
    torch.set_num_threads(plan['threads']);torch.use_deterministic_algorithms(True);torch.manual_seed(plan['seed'])
    f=pd.read_parquet(ROOT/plan['source']).sort_values(['station','time']).reset_index(drop=True)
    extra=pd.read_parquet(ROOT/plan['local_source'],columns=['station','time','ice',*ADDED]).sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(f[['station','time','ice']],extra[['station','time','ice']],check_exact=True)
    assert f.station.nunique()==23 and not set(f.station)&set(plan['blocked_stations'])
    for c in ADDED:assert c not in f;f[c]=extra[c]
    del extra;gc.collect()
    if (out/'feature_receipt.json').exists():
        receipt=read(out/'feature_receipt.json');assert sha(out/'features.parquet')==receipt['sha256']
        features=pd.read_parquet(out/'features.parquet');instantaneous=receipt['instantaneous_columns']
    else:
        original=read(prior/'plan.json');receipt=read(prior/'feature_receipt.json')
        for name in [plan['source'],plan['local_source'],'src/antecedent_forcing.py','src/objective_icing.py','src/anchored_icing.py']:
            assert sha(ROOT/name)==original['signatures'][name]
        assert sha(prior/'features.parquet')==receipt['sha256']
        assert not (prior/'selection.json').exists() and not (prior/'summary.json').exists()
        shutil.copy2(prior/'features.parquet',out/'features.parquet')
        shutil.copy2(prior/'feature_receipt.json',out/'feature_receipt.json')
        features=pd.read_parquet(out/'features.parquet');instantaneous=receipt['instantaneous_columns']
        assert len(features)==len(f) and not set(['station','time','ice','road_temp'])&set(features)
    print('FEATURES',features.shape,'instantaneous',len(instantaneous),flush=True)
    groups=sorted(set(f.group)-{'competition'});keys=[*((g,) for g in groups),*combinations(groups,2)]
    tables={};fits=[];reused=[];new_count=0
    for excluded in keys:
        stem='__'.join(excluded);train=f.loc[~f.group.isin(excluded)&f.available&f.ice.isin([0,1])];query=f.loc[f.group.isin(excluded)]
        assert not set(train.station)&set(query.station)
        scores=query[['station','time','group','winter','ice','available','asos_air_temp']].copy().reset_index(drop=True)
        oldrecord=read(control/(stem+'__bce_day.json'));oldpath=control/oldrecord['model']
        assert sha(oldpath)==oldrecord['sha256'] and sorted(train.station.unique())==oldrecord['train_stations']
        assert len(train)==oldrecord['train_rows']
        with np.load(oldpath,allow_pickle=False) as archive:model={k:archive[k] for k in archive.files}
        with deny_network() as attempts,threadpool_limits(limits=plan['threads']):scores['asos_bce']=correction(query,model)
        assert not attempts
        oldscores=pd.read_parquet(control/(stem+'__scores.parquet'))
        pd.testing.assert_frame_equal(scores[['station','time']].reset_index(drop=True),oldscores[['station','time']].reset_index(drop=True),check_exact=True)
        np.testing.assert_array_equal(scores.asos_bce,oldscores.bce_day)
        reused.append(dict(model=oldpath.relative_to(ROOT).as_posix(),sha256=sha(oldpath),rows=len(query)))
        for candidate in plan['models']:
            columns=instantaneous if candidate=='instantaneous' else list(features)
            path=out/(stem+'__'+candidate+'.npz');recordpath=out/(stem+'__'+candidate+'.json');started=time.perf_counter()
            if recordpath.exists():
                record=read(recordpath);assert sha(path)==record['sha256']
                with np.load(path,allow_pickle=False) as archive:model={k:archive[k] for k in archive.files}
            else:
                if path.exists():raise FileExistsError('Unrecorded fit')
                with deny_network() as attempts,threadpool_limits(limits=plan['threads']):
                    model=fit_forcing(train,features.loc[train.index,columns],plan)
                assert not attempts
                np.savez_compressed(path,**model)
                record=dict(excluded=list(excluded),kind=candidate,model=path.name,sha256=sha(path),
                    train_rows=len(train),train_positive_rows=int(train.ice.sum()),train_stations=sorted(train.station.unique()),
                    features=columns,seconds=time.perf_counter()-started,loss_history=model['history'].tolist())
                write(recordpath,record);new_count+=1
            with deny_network() as attempts,threadpool_limits(limits=plan['threads']):
                scores[candidate]=correction_from_features(features.loc[query.index,columns],model)
            assert not attempts
            fits.append(record);print('FIT',len(fits),'/20',stem,candidate,round(record['seconds'],1),flush=True)
            if args.max_new_fits and new_count>=args.max_new_fits:
                print('CHECKPOINT before outer metric calculation',flush=True);return
        scorepath=out/(stem+'__scores.parquet')
        if scorepath.exists():pd.testing.assert_frame_equal(pd.read_parquet(scorepath),scores,check_exact=True)
        else:scores.to_parquet(scorepath,index=False,compression='zstd')
        tables[excluded]=scores;del train,query,model,oldscores;gc.collect()
    specs=policies({**plan,'models':['asos_bce',*plan['models']]});decisions=[];parts=[]
    for held in groups:
        inner=pd.concat([tables[tuple(sorted([held,other]))].loc[lambda q:q.group.eq(other)] for other in groups if other!=held],ignore_index=True)
        table=metric_table(inner,predictions(inner,specs,plan['cap_c']),specs)
        table.to_csv(out/(held+'__inner.csv'),index=False)
        selected={track:choose(table,track) for track in ['mean_f1','recall_guard']}
        selected['matched_instantaneous']=choose(table.loc[table.model.ne('dose')],'mean_f1')
        decisions.append(dict(held=held,selected=selected))
        q=tables[(held,)].copy();matrix=predictions(q,specs,plan['cap_c'])
        for j,spec in enumerate(specs):q[spec['candidate']]=matrix[:,j]
        for track,name in selected.items():q[track]=q[name]
        parts.append(q)
    write(out/'selection.json',dict(at_utc=now(),decisions=decisions,outer_metrics_computed=False))
    result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    result.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    reports={};days={};tracks=['mean_f1','recall_guard','matched_instantaneous']
    for name in [s['candidate'] for s in specs]+tracks:
        reports[name],days[name],events=report(result,name,plan)
        if name in tracks+['asos_zero']:
            days[name].to_csv(out/(name+'__daily.csv'),index=False);events.to_csv(out/(name+'__events.csv'),index=False)
    for name in reports:
        reports[name]['baseline_calendar_f1']=fixed_calendar_f1(days[name],days['asos_zero'])
    base=reports['asos_zero'];primary=reports['mean_f1'];matched=reports['matched_instantaneous']
    gates=dict(f1_asos=primary['all']['f1_fixed_population']>=1.01*base['all']['f1_fixed_population'],
        f1_matched=primary['all']['f1_fixed_population']>=1.01*matched['all']['f1_fixed_population'],
        precision=primary['all']['precision_available_station_mean']>=base['all']['precision_available_station_mean'],
        recall=primary['all']['recall_available_station_mean']>=base['all']['recall_available_station_mean'],
        winters=all(primary['winters'][y]['f1_fixed_population']>=base['winters'][y]['f1_fixed_population'] for y in base['winters']),
        regions=all(primary['regions'][g]['f1_fixed_population']>=base['regions'][g]['f1_fixed_population'] for g in groups),
        stations=all(primary['all']['station_f1_fixed'][s]>=base['all']['station_f1_fixed'][s] for s in base['all']['station_f1_fixed']),
        events=primary['events']['lost_events']==0,fixed_calendar=primary['baseline_calendar_f1']>=base['baseline_calendar_f1'])
    sensitivity={name:block_sensitivity(days[name],days['asos_zero'],plan['seed']) for name in ['mean_f1','recall_guard']}
    assert verify_preserved()==frozen
    assert signatures=={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    write(out/'summary.json',dict(status='antecedent_forcing_complete',at_utc=now(),fits=fits,reused=reused,
        decisions=decisions,reports=reports,gates=gates,primary_success=all(gates.values()),sensitivity=sensitivity,
        preservation=frozen,production_model_changed=False,new_independent_assessment=False,
        files={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print('COMPLETE',len(fits),'new fits','F1',primary['all']['f1_fixed_population'],gates,flush=True)


if __name__=='__main__':main()
