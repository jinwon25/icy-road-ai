"""고정 열·수분 모델을 구간 DSM 고도 대용값으로 적용할 때의 민감도를 검증한다."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.physical_features import ThermalContext,load_thermal_sources
from src.data_source import competition_archive,sha256_file
from src.validation import assert_training_stations,binary_metrics,daily_scores,macro_scores


def main():
    private=ROOT/'outputs/private';data=pd.read_parquet(private/'physical_features/features.parquet')
    assert_training_stations(data.station.unique())
    heights=pd.read_csv(private/'solar_terrain_features/station_terrain.csv',dtype={'station':str})[['station','dsm_elevation_m']]
    data=data.merge(heights,on='station',validate='many_to_one')
    previous=json.loads((private/'forward_physics/summary.json').read_text(encoding='utf-8'))
    config=previous['config'];columns=previous['feature_sets']['thermal']
    reference=pd.read_parquet(private/'forward_physics/predictions.parquet')
    meta=pd.read_csv(private/'sensor_availability/metadata.csv',dtype={'station':str});meta=meta.loc[meta.kind.eq('RWIS'),['station','route','lat','lon']]
    context=ThermalContext(data,load_thermal_sources(competition_archive(ROOT)),meta)
    frames=[]
    with threadpool_limits(limits=2):
        for held in sorted(data.station.unique()):
            train=data.loc[data.station.ne(held)&data.time.lt(config['train_before'])&data.ice.notna()].copy()
            valid=data.loc[data.station.eq(held)&data.time.ge(config['validate_from'])].copy()
            tx,_=context.features(train,{held});vx,_=context.features(valid,{held})
            train_x,valid_x=pd.concat([train,tx],axis=1),pd.concat([valid,vx],axis=1)
            model=HistGradientBoostingClassifier(**config['model'],class_weight={0:1.,1:config['positive_weight']})
            model.fit(train_x[columns],train.ice.astype(int))
            native=model.predict_proba(valid_x[columns])[:,1]
            original=reference.loc[reference.station.eq(held)].sort_values('time')
            np.testing.assert_allclose(native,original.score_thermal,rtol=1e-12,atol=1e-12)
            valid_x['elevation_m']=valid_x.dsm_elevation_m
            dsm=model.predict_proba(valid_x[columns])[:,1]
            choices=json.loads((private/'forward_physics'/held/'thresholds.json').read_text(encoding='utf-8'))
            threshold=next(r['daily_threshold'] for r in choices if r['candidate']=='thermal')
            result=valid[['station','time','ice','elevation_m','dsm_elevation_m']].copy()
            result['pred_native']=original.pred_daily_thermal.to_numpy();result['pred_dsm']=(dsm>=threshold).astype(int)
            result['score_native']=native;result['score_dsm']=dsm;frames.append(result)
            print(held,'original prediction reproduced; DSM sensitivity complete',flush=True)
    result=pd.concat(frames,ignore_index=True);metrics={}
    for name in ['native','dsm']:
        col='pred_'+name;good=result.loc[result.ice.notna()]
        daily=daily_scores([(r.station,r.time,int(r.ice) if pd.notna(r.ice) else None,int(getattr(r,col))) for r in result.itertuples()],minimum_coverage=1.)
        days=pd.DataFrame(daily);accepted=days.loc[days.accepted];fixed=accepted.loc[(accepted.tp+accepted.fn).gt(0)]
        metrics[name]={'slot_micro':binary_metrics(good.ice.astype(int),good[col]),'daily_station_macro':macro_scores(daily),'fixed_ice_day_f1':float(fixed.groupby('station').f1.mean().mean()),'false_alarm_nonice_days':int(accepted.loc[(accepted.tp+accepted.fn).eq(0),'fp'].gt(0).sum())}
    out=private/'height_transfer';out.mkdir(parents=True,exist_ok=True)
    result.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    summary={'status':'fixed_model_height_proxy_sensitivity','rows':len(result),'metrics':metrics,
             'native_predictions_reproduced':True,'height_difference':(result.dsm_elevation_m-result.elevation_m).groupby(result.station).first().to_dict(),
             'runner_sha256':sha256_file(Path(__file__)),'thresholds_reselected':False,
             'limitations':['Same fixed model and original inner thresholds; only validation location height input replaced.','DSM is not a verified road-deck or station elevation.','This diagnoses deployment mismatch, not an independently tuned new model.','Official heldouts remain excluded.']}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(metrics),flush=True)


if __name__=='__main__':main()
