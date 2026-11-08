import numpy as np
import pandas as pd
import pytest

from scripts.audit_reanalysis_temperature import metrics, equal_nested


def test_temperature_metrics_missing_rows_and_station_macro():
    frame = pd.DataFrame(dict(station=['a', 'a', 'a', 'b', 'c'], road_temp=[-2., 2., 4., 5., np.nan]))
    result = metrics(frame, [-1., 0., np.nan, 9., 3.])
    assert result['pooled']['n'] == 3
    assert result['pooled']['mae'] == pytest.approx(7/3)
    assert result['pooled']['rmse'] == pytest.approx(np.sqrt(7))
    assert result['pooled']['bias'] == 1
    assert result['station_macro']['mae'] == 2.75
    assert result['near_freezing']['n'] == 2
    assert result['near_freezing']['mae'] == 1.5
    assert result['stations']['c'] == dict(n=0, mae=None, rmse=None, bias=None)
    assert equal_nested(result, result) > 10


def test_temperature_metrics_reject_alignment_and_infinity():
    frame = pd.DataFrame(dict(station=['a'], road_temp=[0.]))
    with pytest.raises(ValueError):
        metrics(frame, [])
    with pytest.raises(ValueError):
        metrics(frame, [np.inf])
