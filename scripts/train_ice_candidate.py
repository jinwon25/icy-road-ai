"""개발 지점만으로 고정 열·수분 HGB와 OOF 기반 전역 임계값을 저장한다."""
import json
import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.physical_features import ThermalContext,load_thermal_sources
from src.data_source import competition_archive,sha256_file
from src.validation import assert_training_stations
from src.ice_daily_selection import choose_daily_threshold
from scripts.baseline_ice_logistic import choose_threshold
from scripts.evaluate_physical_ice import threshold_grid


def main():
    private=ROOT/'outputs/private'
    previous=json.loads((private/'physical_ice/summary.json').read_text(encoding='utf-8'))
    config=previous['config'];features=previous['feature_sets']['thermal']
    data=pd.read_parquet(private/'physical_features/features.parquet').reset_index(drop=True)
    assert_training_stations(data.station.unique())
    oof=pd.read_parquet(private/'physical_ice/predictions.parquet').sort_values(['station','time']).reset_index(drop=True)
    reference=data.sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(oof[['station','time','ice']],reference[['station','time','ice']])
    valid=oof.loc[oof.ice.notna()].copy();score=valid.score_thermal_w20.to_numpy()
    slot_threshold,slot_f1=choose_threshold(valid.ice.to_numpy(dtype=int),score)
    daily_threshold,daily_f1,trace=choose_daily_threshold(valid,score,threshold_grid(score))
    meta=pd.read_csv(private/'sensor_availability/metadata.csv',dtype={'station':str});meta=meta.loc[meta.kind.eq('RWIS'),['station','route','lat','lon']]
    archive=competition_archive(ROOT);context=ThermalContext(data,load_thermal_sources(archive),meta)
    train=data.loc[data.ice.notna()].copy();additional,refs=context.features(train,set())
    train_x=pd.concat([train,additional],axis=1)
    model=HistGradientBoostingClassifier(**config['model'],class_weight={0:1.,1:20.})
    with threadpool_limits(limits=2):model.fit(train_x[features],train.ice.astype(int))
    out=private/'model_candidates/ice_thermal_v1';out.mkdir(parents=True,exist_ok=True)
    joblib.dump(model,out/'ice_hgb.joblib')
    sample=train_x[features].sample(n=100,random_state=20260923)
    with threadpool_limits(limits=2):np.testing.assert_allclose(model.predict_proba(sample),joblib.load(out/'ice_hgb.joblib').predict_proba(sample),rtol=0,atol=0)
    trace.to_csv(out/'oof_threshold_trace.csv',index=False,encoding='utf-8-sig')
    (out/'training_references.json').write_text(json.dumps(refs,indent=2),encoding='utf-8')
    card={'status':'development_candidate_not_officially_evaluated','feature_names':features,'model_config':config['model'],'positive_weight':20.,
          'training_stations':sorted(train.station.unique()),'training_rows':len(train),'training_ice':int(train.ice.sum()),
          'default_threshold':daily_threshold,'slot_threshold':slot_threshold,'threshold_objective':'provisional station-first daily F1 on development LOSO scores',
          'oof_calibration_daily_f1':daily_f1,'oof_calibration_slot_f1':slot_f1,'calibration_is_not_independent_performance':True,
          'score_semantics':'Uncalibrated class-weighted model score, not a physical Ice probability or accident probability.',
          'height_source':'Provided static station elevation; segment DSM substitution requires separate height-transfer diagnostic.',
          'archive_sha256':sha256_file(archive),'model_sha256':sha256_file(out/'ice_hgb.joblib'),
          'feature_input_sha256':sha256_file(private/'physical_features/features.parquet'),'oof_sha256':sha256_file(private/'physical_ice/predictions.parquet'),
          'sklearn_version':sklearn.__version__,'official_holdout_used':False,'final_submission_model':False,
          'limitations':['Global threshold is calibrated on all development LOSO results and must not be reported as unbiased validation.',
                         'Classifier remains weak under winter transfer; saved candidate is a reproducible comparison artifact.',
                         'Official protected targets remain excluded; freeze and final evaluation have not occurred.']}
    (out/'model_card.json').write_text(json.dumps(card,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'rows':len(train),'ice':int(train.ice.sum()),'default_threshold':daily_threshold,'slot_threshold':slot_threshold}),flush=True)


if __name__=='__main__':main()
