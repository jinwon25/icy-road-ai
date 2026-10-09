"""검증한 고정 온도 혼합의 도로 구간 추론용 개발 모델을 저장한다."""
import json
import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file
from src.validation import assert_training_stations
from scripts.baseline_ice_logistic import FEATURES,add_time_features


def main():
    private=ROOT/'outputs/private';source=private/'aws_fallback_features/features.parquet'
    data=add_time_features(pd.read_parquet(source));data=data.loc[data.asos_air_temp.notna() & data.road_temp.notna()].copy()
    assert_training_stations(data.station.unique())
    model=make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler(),Ridge(alpha=100.))
    model.fit(data[FEATURES],data.road_temp)
    validation=pd.read_parquet(private/'neighbor_transfer/predictions.parquet');validation=validation.loc[validation.delay_minutes.eq(0)]
    absolute=(validation.pred_blend-validation.road_temp).abs()
    q=float(absolute.quantile(.9));coverage=validation.assign(within=absolute.le(q)).groupby('station').within.mean().to_dict()
    out=private/'model_candidates/temperature_v1';out.mkdir(parents=True,exist_ok=True)
    joblib.dump(model,out/'weather_ridge.joblib')
    sample=data[FEATURES].sample(n=100,random_state=20260923)
    np.testing.assert_allclose(model.predict(sample),joblib.load(out/'weather_ridge.joblib').predict(sample),rtol=0,atol=0)
    card={'status':'development_candidate_for_retrospective_segment_inference','training_stations':sorted(data.station.unique()),'training_rows':len(data),
          'feature_names':FEATURES,'ridge_alpha':100.,'blend_weather_weight':.5,'neighbor_max_age_minutes':60,'neighbor_strictly_prior':True,
          'missing_neighbor_policy':'weather_ridge_only','missing_asos_policy':'output_unknown_to_preserve_validated_domain',
          'source_sha256':sha256_file(source),'model_sha256':sha256_file(out/'weather_ridge.joblib'),'sklearn_version':sklearn.__version__,
          'development_validation':json.loads((private/'neighbor_transfer/summary.json').read_text(encoding='utf-8')),
          'absolute_error_p90_reference_c':q,'reference_coverage_by_station':coverage,
          'uncertainty_semantics':'Empirical development residual sensitivity radius, not a calibrated prediction interval or coverage guarantee at new road locations.',
          'official_holdout_used':False,'final_submission_model':False}
    (out/'model_card.json').write_text(json.dumps(card,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'training_rows':len(data),'absolute_error_p90_reference_c':q,'coverage_min':min(coverage.values()),'coverage_max':max(coverage.values())}),flush=True)


if __name__=='__main__':main()
