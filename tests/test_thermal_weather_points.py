import numpy as np
import pandas as pd
import pytest
from src.thermal_weather_points import strictly_prior_values


def test_asof_exact_and_stale_and_future():
    source=pd.DataFrame({'source_time':pd.to_datetime(['2024-11-01 00:00','2024-11-01 01:00']), 'value':[10.,20.]})
    times=pd.DatetimeIndex(['2024-11-01 00:00','2024-11-01 00:10','2024-11-01 01:00','2024-11-01 02:00','2024-11-01 02:10'])
    result=strictly_prior_values(times,source,['value'])[:,0]
    np.testing.assert_allclose(result,[np.nan,10.,10.,20.,np.nan],equal_nan=True)
    with pytest.raises(ValueError):strictly_prior_values(times,pd.concat([source,source]),['value'])
