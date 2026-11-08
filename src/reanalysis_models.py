"""현재 기상 63변수에 사후 ERA5-Land 상태를 더하는 고정 입력 대조."""
import numpy as np
import pandas as pd
from src.solar_memory_search import feature_table as solar_features
from src.reanalysis_inputs import FIELDS


def added_columns(kind):
    columns=['era5_'+c for c in FIELDS]
    if kind=='era5_memory':
        columns += ['era5_'+c+'_mean'+str(h)+'h' for c in
                    ['temperature_2m','soil_temperature_0_to_7cm','soil_moisture_0_to_7cm','snow_depth'] for h in [6,24,72]]
    elif kind!='era5_raw':raise ValueError('Unknown predeclared ERA5-Land input set')
    return columns


def feature_table(frame,kind,base=None):
    base=solar_features(frame,'combined_asos_solar') if base is None else base
    if not base.index.equals(frame.index) or len(base.columns)!=63:raise ValueError('Aligned canonical baseline features required')
    x=pd.concat([base,frame[added_columns(kind)].astype(float)],axis=1)
    if x.columns.duplicated().any() or np.isinf(x.to_numpy()).any():raise ValueError('Unique finite or missing input features required')
    return x
