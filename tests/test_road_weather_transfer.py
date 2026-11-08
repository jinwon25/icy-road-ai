import io
import zipfile

import numpy as np
import pandas as pd

from src.road_weather_transfer import (ASOS_FIELDS, AWS_FIELDS, allowed_csv, baselines,
    balanced_weights, clean_target, constrain, features, regression_numbers)


def test_blocked_csv_targets_never_returned():
    content = '관측 지점번호,목표,이름\n12103,1,허용\n12410,비밀,제외\n23202,2,허용\n'
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z: z.writestr('test.csv', content.encode('utf-8-sig'))
    with zipfile.ZipFile(data) as z:
        result, skipped = allowed_csv(z, 'test.csv', ['12103','23202'], ['관측 지점번호','목표'])
    assert result['목표'].tolist() == ['1','2'] and skipped == 1


def sample():
    f = pd.DataFrame({('asos_'+c): [2.,3.,4.,5.] for c in ASOS_FIELDS})
    for c in AWS_FIELDS: f['aws_'+c] = [10.,11.,12.,13.]
    for c in ['hour_sin','hour_cos','season_sin','season_cos','asos_distance_km',
              'aws_distance_km','solar_altitude_deg','solar_sine_positive']: f[c]=1.
    f['asos_age_minutes']=[60.,10.,0.,61.]; f['aws_age_minutes']=[15.,16.,0.,-10.]
    return f


def test_age_and_target_leakage_contract():
    f=sample(); x=features(f)
    f['road_temp']=-100.; f['ice']=1; f['relative_humidity']=0.; f['year']=2029; f['station']='x'
    pd.testing.assert_frame_equal(x,features(f))
    assert x.aws_air_temp.iloc[0]==10 and x.aws_air_temp.iloc[1:].isna().all()
    assert x.asos_air_temp.iloc[2:].isna().all()
    a,b=baselines(f,'air_temperature')
    np.testing.assert_allclose(a,[2,3,np.nan,np.nan],equal_nan=True)
    np.testing.assert_allclose(b,[10,3,np.nan,np.nan],equal_nan=True)


def test_missing_codes_and_physical_output():
    y=clean_target(pd.Series(['-99.9','-30','inf','101','0','100']),[0,100])
    assert y.iloc[:4].isna().all() and y.iloc[4:].tolist()==[0,100]
    assert constrain(np.array([-4,50,110]),'relative_humidity').tolist()==[0,50,100]
    assert constrain(np.array([-4,50]),'air_temperature').tolist()==[-4,50]


def test_station_winter_weights_and_metrics():
    f=pd.DataFrame(dict(station=['a','a','b'],winter=[2024,2024,2025]))
    w=balanced_weights(f)
    assert np.isclose(w[:2].sum(),w[2]) and np.isclose(w.mean(),1)
    result=regression_numbers([0,2,np.nan],[1,4,20])
    assert result['n']==2 and result['mae']==1.5 and result['bias']==1.5
    assert np.isclose(result['rmse'],np.sqrt(2.5))
