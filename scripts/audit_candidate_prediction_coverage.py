"""배포 후보의 입력부족을 허용 개발 정답 범위에서 감사한다. 부분 점수를 새로 고르지 않는다."""
from datetime import datetime,timezone
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_method_blending import read,write,preservation
from src.method_blending import domain
from src.data_source import sha256_file as sha

PRIVATE=ROOT/'outputs/private';OUT=PRIVATE/'candidate_coverage_review_20261014_v1'


def main():
    if OUT.exists():raise FileExistsError('Preserve coverage audit')
    freeze=preservation();OUT.mkdir()
    fixed=PRIVATE/'qa633_development_20261013_v1/fixed_predictions.parquet'
    controls=PRIVATE/'weather_memory_controls_20261013_v1/ice_predictions.parquet'
    weather=PRIVATE/'weather_distance_20261010_v1/development_inputs.parquet'
    frame=domain(pd.read_parquet(fixed,columns=['station','time','ice','equal_nohistory_pair']))
    values=pd.read_parquet(controls,columns=['station','time','nohistory12_mse300','nohistory12_mae300','baseline_prediction'])
    water=pd.read_parquet(weather,columns=['station','time','asos_air_temp','asos_age_minutes','aws_dewpoint','rain15_max_3h','asos_snow_cm'])
    f=frame.merge(values,on=['station','time'],validate='one_to_one').merge(water,on=['station','time'],validate='one_to_one');domain(f)
    t=(f.nohistory12_mse300.to_numpy()+f.nohistory12_mae300.to_numpy())/2
    w=f[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].to_numpy()
    valid_temperature=np.isfinite(t)&f.asos_air_temp.notna().to_numpy()&f.asos_age_minutes.between(0,60).to_numpy()
    valid_water=~np.isnan(w).all(axis=1);valid=valid_temperature&valid_water
    p=((t<=0)&((w[:,0]>=t)|(w[:,1]>0)|(w[:,2]>0))).astype(float);p[~valid]=np.nan
    np.testing.assert_array_equal(p[valid],f.equal_nohistory_pair.to_numpy()[valid])
    f['runtime_prediction']=p;f['prediction_available']=valid;f['temperature_available']=valid_temperature;f['moisture_available']=valid_water
    f['date_kst']=f.time.dt.normalize();missing=f.loc[~valid].copy()
    missing.to_csv(OUT/'development_input_missing_rows.csv',index=False,encoding='utf-8-sig')
    station=[];days=[]
    for st,d in f.groupby('station'):
        station.append(dict(station=st,rows=len(d),predictions_available=int(d.prediction_available.sum()),missing_predictions=int((~d.prediction_available).sum()),
            valid_ice_labels=int(d.ice.notna().sum()),positive_ice_labels=int(d.ice.eq(1).sum()),
            positive_labels_on_missing_inputs=int((~d.prediction_available&d.ice.eq(1)).sum()),negative_labels_on_missing_inputs=int((~d.prediction_available&d.ice.eq(0)).sum())))
    for (st,date),d in f.groupby(['station','date_kst']):
        if not d.prediction_available.all():
            days.append(dict(station=st,date_kst=str(date.date()),query_rows=len(d),prediction_rows=int(d.prediction_available.sum()),
                missing_predictions=int((~d.prediction_available).sum()),valid_labels=int(d.ice.notna().sum()),
                positive_labels=int(d.ice.eq(1).sum()),positive_labels_on_missing_inputs=int((~d.prediction_available&d.ice.eq(1)).sum())))
    pd.DataFrame(station).to_csv(OUT/'development_station_coverage.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(days).to_csv(OUT/'development_partial_prediction_days.csv',index=False,encoding='utf-8-sig')
    # 보호측은 예측의가용성만 읽으며실제관측·평가파일과결합하지 않는다.
    target=PRIVATE/'submission_candidate_20261013_v1/data/protected_predictions_10min.csv.gz'
    protected=pd.read_csv(target,usecols=['station','time','estimated_road_temp_c','predicted_ice'],dtype={'station':str},parse_dates=['time'])
    assert len(protected)==103680 and not protected.duplicated(['station','time']).any()
    protected_missing=protected.loc[protected.predicted_ice.isna()];protected_missing.to_csv(OUT/'protected_prediction_missing_slots.csv',index=False,encoding='utf-8-sig')
    protected_counts=protected.assign(missing=protected.predicted_ice.isna(),date_kst=protected.time.dt.normalize()).groupby('station').agg(rows=('time','size'),missing_predictions=('missing','sum')).reset_index()
    protected_counts.to_csv(OUT/'protected_prediction_coverage.csv',index=False,encoding='utf-8-sig')
    assert len(protected_missing)==18
    signatures={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),fixed,controls,weather,target,ROOT/'src/submission_runtime.py',ROOT/'src/submission_io.py']}
    assert preservation()==freeze
    write(OUT/'summary.json',dict(status='candidate_prediction_coverage_verified',checked_at_utc=datetime.now(timezone.utc).isoformat(),
        development_rows=len(f),available_prediction_rows=int(valid.sum()),missing_prediction_rows=len(missing),
        labelled_ice_on_missing_inputs=int(missing.ice.eq(1).sum()),labelled_negative_on_missing_inputs=int(missing.ice.eq(0).sum()),
        unknown_labels_on_missing_inputs=int(missing.ice.isna().sum()),affected_development_dates=len(days),
        defined_prediction_values_verified=int(valid.sum()),original_fallback_positive_rows=int(missing.equal_nohistory_pair.sum()),
        protected_prediction_rows=len(protected),protected_missing_prediction_rows=len(protected_missing),protected_ground_truth_read=False,
        source_metric_denominator_changed=False,new_official_score_computed=False,new_models_fitted=0,model_promoted=False,
        missing_prediction_penalty_officially_confirmed=False,submission_csv_null_encoding_confirmed=False,
        input_signatures=signatures,old_frozen_files=freeze[0],reserved_frozen_files=freeze[1]))
    print(read(OUT/'summary.json'))


if __name__=='__main__':main()
