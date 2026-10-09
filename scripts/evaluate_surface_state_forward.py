"""다른 개발 지점의 과거 노면상태 추가 효과를 겨울·공간 분리로 비교한다."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
import joblib
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import competition_archive,sha256_file
from src.physical_features import load_thermal_sources,CONTEXT_FEATURES
from src.surface_state_context import SurfaceStateContext, STATE_FEATURES
from sklearn.metrics import average_precision_score, roc_auc_score
from src.ice_daily_selection import choose_daily_threshold
from src.validation import assert_training_stations,binary_metrics,daily_scores,macro_scores
from scripts.baseline_ice_logistic import FEATURES,choose_threshold
from scripts.evaluate_physical_ice import threshold_grid


def main():
    private=ROOT/'outputs/private'
    config_path=ROOT/'config/surface_state_forward_experiment.json'
    config=json.loads(config_path.read_text(encoding='utf-8'))
    feature_path=private/'physical_features/features.parquet'
    data=pd.read_parquet(feature_path).reset_index(drop=True)
    assert_training_stations(data.station.unique())
    physical=json.loads((private/'physical_features/summary.json').read_text(encoding='utf-8'))
    features={'surface_state':FEATURES+physical['additional_features']+CONTEXT_FEATURES+STATE_FEATURES}
    split_path=private/'validation/splits.json'
    splits=json.loads(split_path.read_text(encoding='utf-8'))['outer_folds']
    meta=pd.read_csv(private/'sensor_availability/metadata.csv',dtype={'station':str})
    meta=meta.loc[meta.kind.eq('RWIS'),['station','route','lat','lon']]
    archive=competition_archive(ROOT)
    states=data[['station','time','state_raw']].copy()
    context=SurfaceStateContext(data,load_thermal_sources(archive),meta,states)
    out=private/'surface_state_forward';out.mkdir(parents=True,exist_ok=True)
    signature={'features':sha256_file(feature_path),'config':sha256_file(config_path),'splits':sha256_file(split_path),
               'runner':sha256_file(Path(__file__)),'context':sha256_file(ROOT/'src/physical_features.py'),'state_code':sha256_file(ROOT/'src/surface_state_context.py'),'archive':sha256_file(archive)}
    manifest=out/'input_signature.json'
    if manifest.exists() and json.loads(manifest.read_text(encoding='utf-8'))!=signature:
        raise ValueError('Changed experiment signature; preserve outputs')
    manifest.write_text(json.dumps(signature,indent=2),encoding='utf-8')
    frames,choices=[],[]
    with threadpool_limits(limits=config['max_compute_threads']):
        for outer in splits:
            held=str(outer['validation_station']);folder=out/held;folder.mkdir(exist_ok=True)
            final=folder/'predictions.parquet'
            if final.exists():
                frames.append(pd.read_parquet(final));choices.extend(json.loads((folder/'thresholds.json').read_text(encoding='utf-8')))
                print(held,'reused',flush=True);continue
            train=data.loc[data.station.ne(held)&data.time.lt(config['train_before'])&data.ice.notna()].copy()
            valid=data.loc[data.station.eq(held)&data.time.ge(config['validate_from'])].copy()
            if train.time.max()>=valid.time.min() or set(train.station)!=set(outer['training_stations']):
                raise AssertionError('Space/time partition mismatch')
            oof={name:np.full(len(train),np.nan) for name in config['candidates']};refs=[]
            for k,inner in enumerate(outer['inner_folds']):
                mask=train.station.isin(inner['stations']).to_numpy();fit,check=train.loc[~mask],train.loc[mask]
                forbidden=set(inner['stations'])|{held}
                tx,r1=context.features(fit,forbidden);vx,r2=context.features(check,forbidden)
                fit_x,check_x=pd.concat([fit,tx],axis=1),pd.concat([check,vx],axis=1)
                refs.extend([{**r,'fold':k,'role':role} for role,rs in [('fit',r1),('check',r2)] for r in rs])
                for name in config['candidates']:
                    model=HistGradientBoostingClassifier(**config['model'],class_weight={0:1.,1:config['positive_weight']})
                    model.fit(fit_x[features[name]],fit.ice.astype(int));oof[name][mask]=model.predict_proba(check_x[features[name]])[:,1]
                print(held,f'inner {k+1}/3 complete',flush=True)
            tx,r1=context.features(train,{held});vx,r2=context.features(valid,{held})
            train_x,valid_x=pd.concat([train,tx],axis=1),pd.concat([valid,vx],axis=1)
            refs.extend([{**r,'fold':None,'role':role} for role,rs in [('outer_fit',r1),('outer_check',r2)] for r in rs])
            result=valid[['station','time','ice']].copy();thresholds=[];inner_output=train[['station','time','ice']].copy()
            for name in config['candidates']:
                scores=oof[name]
                if not np.isfinite(scores).all():raise AssertionError('Missing OOF')
                slot_t,slot_f1=choose_threshold(train.ice.to_numpy(dtype=int),scores)
                daily_t,daily_f1,trace=choose_daily_threshold(train,scores,threshold_grid(scores))
                thresholds.append({'station':held,'candidate':name,'slot_threshold':slot_t,'daily_threshold':daily_t,'inner_slot_f1':slot_f1,'inner_daily_f1':daily_f1})
                trace.to_csv(folder/f'{name}_trace.csv',index=False);inner_output[f'score_{name}']=scores
                model=HistGradientBoostingClassifier(**config['model'],class_weight={0:1.,1:config['positive_weight']})
                model.fit(train_x[features[name]],train.ice.astype(int));score=model.predict_proba(valid_x[features[name]])[:,1]
                if not np.isfinite(score).all():raise AssertionError('Nonfinite score')
                joblib.dump(model,folder/f'{name}_development_model.joblib')
                result[f'score_{name}']=score;result[f'pred_slot_{name}']=(score>=slot_t).astype(int);result[f'pred_daily_{name}']=(score>=daily_t).astype(int)
            inner_output.to_parquet(folder/'inner_oof.parquet',index=False,compression='zstd')
            (folder/'thresholds.json').write_text(json.dumps(thresholds,indent=2),encoding='utf-8')
            (folder/'references.json').write_text(json.dumps(refs,indent=2),encoding='utf-8')
            result.to_parquet(final,index=False,compression='zstd');frames.append(result);choices.extend(thresholds)
            print(held,'next-winter complete',flush=True)
    result=pd.concat(frames,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    reference=pd.read_parquet(private/'forward_physics/predictions.parquet').sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(result[['station','time','ice']],reference[['station','time','ice']])
    for column in ['score_thermal','pred_slot_thermal','pred_daily_thermal']:result[column]=reference[column]
    metrics={};days_all=[]
    for name in ['thermal',*config['candidates']]:
        for policy in ['slot','daily']:
            col=f'pred_{policy}_{name}';good=result.loc[result.ice.notna()]
            records=[(r.station,r.time,int(r.ice) if pd.notna(r.ice) else None,int(getattr(r,col))) for r in result.itertuples()]
            daily=daily_scores(records,minimum_coverage=1.);days=pd.DataFrame(daily);accepted=days.loc[days.accepted]
            fixed=accepted.loc[(accepted.tp+accepted.fn).gt(0)]
            metrics[f'{name}_{policy}']={'slot_micro':binary_metrics(good.ice.astype(int),good[col]),'average_precision':float(average_precision_score(good.ice,good[f'score_{name}'])),'roc_auc':float(roc_auc_score(good.ice,good[f'score_{name}'])),'daily_station_macro':macro_scores(daily),
                                         'fixed_ice_day_f1':float(fixed.groupby('station').f1.mean().mean()),'false_alarm_nonice_days':int(accepted.loc[(accepted.tp+accepted.fn).eq(0),'fp'].gt(0).sum())}
            days['variant']=f'{name}_{policy}';days_all.append(days)
    result.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    pd.DataFrame(choices).to_csv(out/'thresholds.csv',index=False);pd.concat(days_all).to_csv(out/'daily_metrics.csv',index=False,encoding='utf-8-sig')
    summary={'status':'surface_state_space_winter_forward_development_only','rows':len(result),'metrics':metrics,'feature_sets':features,'config':config,'signature':signature}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(metrics),flush=True)


if __name__=='__main__':main()
