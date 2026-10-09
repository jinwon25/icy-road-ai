"""관측소와 구간의 DSM 높이 정의를 일치시킨 별도 열·수분 검증."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import competition_archive,sha256_file
from src.physical_features import ThermalContext,load_thermal_sources,CONTEXT_FEATURES
from src.moisture_memory import MEMORY_FEATURES
from src.ice_daily_selection import choose_daily_threshold
from src.validation import assert_training_stations,binary_metrics,daily_scores,macro_scores
from scripts.baseline_ice_logistic import FEATURES,choose_threshold
from scripts.evaluate_physical_ice import threshold_grid


def main():
    private=ROOT/'outputs/private'
    config_path=ROOT/'config/dsm_consistent_experiment.json'
    config=json.loads(config_path.read_text(encoding='utf-8'))
    feature_path=private/'moisture_memory/features.parquet'
    data=pd.read_parquet(feature_path).reset_index(drop=True)
    height_path=private/'solar_terrain_features/station_terrain.csv'
    heights=pd.read_csv(height_path,dtype={'station':str})[['station','dsm_elevation_m']].rename(columns={'dsm_elevation_m':'site_height_m'})
    data=data.merge(heights,on='station',validate='many_to_one')
    if data.site_height_m.isna().any():raise ValueError('Missing consistent DSM height')
    assert_training_stations(data.station.unique())
    physical=json.loads((private/'physical_features/summary.json').read_text(encoding='utf-8'))
    features={'thermal_dsm':FEATURES+[c for c in physical['additional_features'] if c!='elevation_m']+CONTEXT_FEATURES+['site_height_m']}
    split_path=private/'validation/splits.json'
    splits=json.loads(split_path.read_text(encoding='utf-8'))['outer_folds']
    meta=pd.read_csv(private/'sensor_availability/metadata.csv',dtype={'station':str})
    meta=meta.loc[meta.kind.eq('RWIS'),['station','route','lat','lon']]
    archive=competition_archive(ROOT)
    context=ThermalContext(data,load_thermal_sources(archive),meta)
    out=private/'dsm_consistent';out.mkdir(parents=True,exist_ok=True)
    signature={'height_source':sha256_file(height_path),'features':sha256_file(feature_path),'config':sha256_file(config_path),'splits':sha256_file(split_path),
               'runner':sha256_file(Path(__file__)),'context':sha256_file(ROOT/'src/physical_features.py'),'archive':sha256_file(archive)}
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
                result[f'score_{name}']=score;result[f'pred_slot_{name}']=(score>=slot_t).astype(int);result[f'pred_daily_{name}']=(score>=daily_t).astype(int)
            inner_output.to_parquet(folder/'inner_oof.parquet',index=False,compression='zstd')
            (folder/'thresholds.json').write_text(json.dumps(thresholds,indent=2),encoding='utf-8')
            (folder/'references.json').write_text(json.dumps(refs,indent=2),encoding='utf-8')
            result.to_parquet(final,index=False,compression='zstd');frames.append(result);choices.extend(thresholds)
            print(held,'next-winter complete',flush=True)
    result=pd.concat(frames,ignore_index=True);metrics={};days_all=[]
    for name in config['candidates']:
        for policy in ['slot','daily']:
            col=f'pred_{policy}_{name}';good=result.loc[result.ice.notna()]
            records=[(r.station,r.time,int(r.ice) if pd.notna(r.ice) else None,int(getattr(r,col))) for r in result.itertuples()]
            daily=daily_scores(records,minimum_coverage=1.);days=pd.DataFrame(daily);accepted=days.loc[days.accepted]
            fixed=accepted.loc[(accepted.tp+accepted.fn).gt(0)]
            metrics[f'{name}_{policy}']={'slot_micro':binary_metrics(good.ice.astype(int),good[col]),'daily_station_macro':macro_scores(daily),
                                         'fixed_ice_day_f1':float(fixed.groupby('station').f1.mean().mean()),'false_alarm_nonice_days':int(accepted.loc[(accepted.tp+accepted.fn).eq(0),'fp'].gt(0).sum())}
            days['variant']=f'{name}_{policy}';days_all.append(days)
    result.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    pd.DataFrame(choices).to_csv(out/'thresholds.csv',index=False);pd.concat(days_all).to_csv(out/'daily_metrics.csv',index=False,encoding='utf-8-sig')
    summary={'status':'consistent_dsm_space_winter_forward','rows':len(result),'metrics':metrics,'feature_sets':features,'config':config,'signature':signature}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(metrics),flush=True)


if __name__=='__main__':main()
