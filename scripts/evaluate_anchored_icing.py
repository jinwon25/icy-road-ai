"""ASOS 기준선의 제한 보정 56개와 온도 문턱 대조 8개를 지역 이중 제외로 비교한다."""
import argparse,time,warnings
from itertools import combinations
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.anchored_icing import linear_features,anchored_prediction,binary_matrix_metrics,choose_policy
from src.synoptic_icing import sample_weights
from src.two_winter import validate
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.evaluate_synoptic_icing import read,write,KEYS,report_predictions,assert_matching_keys
from scripts.evaluate_thermal_classification import available
from scripts.evaluate_method_blending import preservation


def specifications(plan,model_names):
    specs={}
    for name in model_names:
        for bound in plan['correction_bounds']:
            for direction in plan['directions']:
                key=f'{name}_{direction}_{bound:g}'
                specs[key]=dict(model=name,bound=bound,direction=direction,complexity=1+bound)
    for threshold in plan['constant_threshold_controls']:
        specs[f'air_threshold_{threshold:g}']=dict(threshold=threshold,complexity=abs(threshold))
    specs['asos_zero']=dict(threshold=0.,complexity=0.)
    return specs


def policy_matrix(frame,score_map,specs):
    columns=[]
    for spec in specs.values():
        p=frame.asos_air_temp.le(spec['threshold']).to_numpy(float) if 'threshold' in spec else anchored_prediction(frame.asos_air_temp,score_map[spec['model']],spec['bound'],spec['direction'])
        columns.append(np.where(frame.available,p,np.nan))
    return np.column_stack(columns)


def selection_table(frame,predictions,specs):
    table=binary_matrix_metrics(frame,predictions)
    for year in [2024,2025]:
        mask=frame.winter.eq(year);table['f1_'+str(year)]=binary_matrix_metrics(frame.loc[mask],predictions[mask])['mean_f1'].to_numpy()
    table['worst_winter_f1']=table[['f1_2024','f1_2025']].min(axis=1)
    table['candidate']=list(specs);table['complexity']=[s['complexity'] for s in specs.values()]
    return table


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);out=p.parse_args().output.resolve()
    config=ROOT/'config/icing_anchor_20261025.json';plan=read(config)
    paths=[config,Path(__file__),ROOT/'src/anchored_icing.py',ROOT/'src/synoptic_icing.py',ROOT/'scripts/evaluate_synoptic_icing.py',
           ROOT/plan['data'],ROOT/plan['baseline'],ROOT/plan['prior_study']/'summary.json',ROOT/plan['prior_audit']]
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    if not out.is_relative_to((ROOT/'outputs/private').resolve()):raise ValueError('Private output required')
    if out.exists():
        assert read(out/'plan.json')['signatures']==signatures
        if (out/'summary.json').exists():raise FileExistsError('Preserve completed experiment')
    else:out.mkdir(parents=True);write(out/'plan.json',dict(settings=plan,signatures=signatures))
    frozen=preservation();data=validate(pd.read_parquet(ROOT/plan['data'])).sort_values(['station','time']).reset_index(drop=True)
    assert sha(ROOT/plan['data'])==read((ROOT/plan['data']).parent/'receipt.json')['data_sha256']
    prior=ROOT/plan['prior_study'];audit=read(ROOT/plan['prior_audit'])
    assert audit['status']=='synoptic_icing_independently_verified' and audit['summary_sha256']==sha(prior/'summary.json')
    prior_names=[s['name'] for s in read(prior/'plan.json')['settings']['candidates']]
    groups=sorted(set(data.group)-{'competition'});contexts=[*((g,) for g in groups),*combinations(groups,2)]
    valid=available(data);x=linear_features(data);stores={n:{} for n in prior_names};fits=[]
    for name in prior_names:
        for key in contexts:
            stem='__'.join(key);record=read(prior/name/(stem+'.json'));path=prior/name/(stem+'.parquet')
            assert sha(path)==record['prediction_sha256'];stores[name][key]=pd.read_parquet(path)
    for spec in plan['linear_models']:
        name=spec['name'];stores[name]={};folder=out/name;folder.mkdir(exist_ok=True)
        for key in contexts:
            stem='__'.join(key);recordpath=folder/(stem+'.json');modelpath=folder/(stem+'.joblib');predpath=folder/(stem+'.parquet')
            qm=data.group.isin(key);tm=~qm&valid&data.ice.isin([0,1]);train=data.loc[tm]
            assert not set(train.station)&set(data.loc[qm,'station']) and set(train.winter)=={2024,2025}
            if recordpath.exists():
                record=read(recordpath);assert sha(modelpath)==record['model_sha256'] and sha(predpath)==record['prediction_sha256'];q=pd.read_parquet(predpath)
            else:
                model=make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler(),LogisticRegression(**plan['parameters']))
                w=sample_weights(train,spec['weights']);start=time.perf_counter()
                with warnings.catch_warnings(),deny_network() as attempts,threadpool_limits(limits=2):
                    warnings.simplefilter('error',ConvergenceWarning)
                    model.fit(x.loc[tm],train.ice.to_numpy(int),logisticregression__sample_weight=w)
                    score=model.predict_proba(x.loc[qm])[:,1]
                assert not attempts and np.isfinite(score).all()
                q=data.loc[qm,KEYS].copy();q['available']=valid[qm];q['score']=score
                joblib.dump(model,modelpath,compress=3);q.to_parquet(predpath,index=False,compression='zstd')
                record=dict(candidate=name,excluded_groups=list(key),training_stations=sorted(train.station.unique()),query_stations=sorted(data.loc[qm,'station'].unique()),
                    training_rows=len(train),query_rows=int(qm.sum()),features=list(x),weights=spec['weights'],parameters=plan['parameters'],
                    training_weight_sum=float(w.sum()),weighted_positive_fraction=float(np.average(train.ice,weights=w)),
                    model_sha256=sha(modelpath),prediction_sha256=sha(predpath),iterations=model[-1].n_iter_.tolist(),seconds=time.perf_counter()-start)
                write(recordpath,record);print('FIT',name,stem,round(record['seconds'],1),flush=True)
            stores[name][key]=q;fits.append(record);write(out/'progress.json',dict(models_complete=len(fits),planned_models=20))
    specs=specifications(plan,list(stores));assert len(specs)==65;write(out/'policies.json',specs)
    parts=[];decisions={}
    for outer in groups:
        held=[g for g in groups if g!=outer];chunks=[];scores={n:[] for n in stores}
        for h in held:
            key=tuple(sorted([outer,h]));q=stores[next(iter(stores))][key].loc[lambda f:f.group.eq(h),KEYS+['available']].copy();chunks.append(q)
            for name,cache in stores.items():
                other=cache[key].loc[lambda f:f.group.eq(h)];assert_matching_keys(other,q);scores[name].append(other.score.to_numpy())
        inner=pd.concat(chunks,ignore_index=True);scores={n:np.concatenate(v) for n,v in scores.items()}
        table=selection_table(inner,policy_matrix(inner,scores,specs),specs);table.to_csv(out/(outer+'_selection.csv'),index=False)
        q=stores[next(iter(stores))][(outer,)][KEYS+['available']].copy();scores={}
        for name,cache in stores.items():assert_matching_keys(cache[(outer,)],q);scores[name]=cache[(outer,)].score.to_numpy()
        matrix=policy_matrix(q,scores,specs)
        part=pd.concat([q.reset_index(drop=True),pd.DataFrame(matrix,columns=specs)],axis=1);decisions[outer]={}
        for track in plan['selection_tracks']:
            choice=choose_policy(table,track);decisions[outer][track]=choice
            part['selected_'+track]=part[choice['candidate']]
        parts.append(part);print('SELECT',outer,{k:v['candidate'] for k,v in decisions[outer].items()},flush=True)
    result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    base=validate(pd.read_parquet(ROOT/plan['baseline'])).sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(result[KEYS],base[KEYS]);np.testing.assert_array_equal(result.available,base.physical_both.notna())
    result['current']=base.physical_both.to_numpy();reports=report_predictions(result,out)
    write(out/'decisions.json',decisions);write(out/'fit_receipts.json',fits);assert preservation()==frozen
    write(out/'summary.json',dict(status='anchored_icing_comparison_complete',new_fits=len(fits),cached_model_fits=50,reports=reports,
        source_signatures=signatures,protected_labels_read=False,new_independent_assessment=False,production_model_changed=False,
        frozen_counts=list(frozen),files={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='summary.json'}))


if __name__=='__main__':main()
