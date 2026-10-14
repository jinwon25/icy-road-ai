from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from src.submission_io import read_weather


class SubmissionIOTests(unittest.TestCase):
    def test_csv_roundtrip_exact_float_and_station_identity(self):
        f=pd.DataFrame({'station':['001']*200,'value':np.random.default_rng(27).normal(size=200),
            'cycle':np.cos(np.arange(200)/17)})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'weather.csv';f.to_csv(path,index=False);actual=read_weather(path)
            pd.testing.assert_frame_equal(actual,f,check_exact=True)

    def test_parquet_missing_values_preserved(self):
        f=pd.DataFrame({'station':['001','002'],'value':[np.nan,-2.]})
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'weather.parquet';f.to_parquet(path,index=False)
            pd.testing.assert_frame_equal(read_weather(path),f,check_exact=True)


if __name__=='__main__':unittest.main()
