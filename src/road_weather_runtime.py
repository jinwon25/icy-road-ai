"""별도 기상 추정 보완 모형. 기존 노면온도·결빙 모델의 입력을 변경하지 않는다."""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from src.data_source import sha256_file
from src.road_weather_transfer import ASOS_FIELDS,AWS_FIELDS,features,baselines,constrain


INPUT_COLUMNS = ['asos_'+s for s in ASOS_FIELDS]+['aws_'+s for s in AWS_FIELDS]+[
    'asos_age_minutes','aws_age_minutes','hour_sin','hour_cos','season_sin','season_cos',
    'asos_distance_km','aws_distance_km','solar_altitude_deg','solar_sine_positive']
OUTPUT_COLUMNS = {'air_temperature':'estimated_air_temperature_c',
    'relative_humidity':'estimated_humidity_pct','wind_speed':'estimated_wind_speed_ms'}


def predict_weather(frame,model_directory):
    """28개 기상 입력에서 검증된 목표만 추정한다. 가용하지 않은 행은 결측으로 둔다."""
    directory=Path(model_directory)
    metadata=json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
    if metadata['format']!='road_weather_residual_v1':raise ValueError('Unsupported weather model format')
    if set(INPUT_COLUMNS)-set(frame):raise ValueError('Required weather input columns missing')
    if not metadata['targets'] or set(metadata['targets'])-set(OUTPUT_COLUMNS):raise ValueError('Invalid weather target list')
    x=features(frame[INPUT_COLUMNS])
    if list(x)!=metadata['features']:raise ValueError('Weather feature schema mismatch')
    result=frame.loc[:,[c for c in ['station','time'] if c in frame]].copy()
    for target,spec in metadata['targets'].items():
        path=directory/spec['file']
        if path.parent.resolve()!=directory.resolve() or path.suffix!='.joblib':raise ValueError('Invalid model path')
        if sha256_file(path)!=spec['sha256']:raise ValueError('Weather model checksum mismatch')
        model=joblib.load(path)
        if list(model.feature_names_in_)!=list(x):raise ValueError('Stored estimator feature mismatch')
        asos,baseline=baselines(frame,target);available=np.isfinite(asos)&np.isfinite(baseline)
        prediction=np.full(len(frame),np.nan)
        if available.any():
            with threadpool_limits(limits=2):values=model.predict(x.loc[available])+baseline[available]
            prediction[available]=constrain(values,target)
        column=OUTPUT_COLUMNS[target];result[column]=prediction;result[column+'_available']=available
    return result
