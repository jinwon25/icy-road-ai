import numpy as np
import pandas as pd
import pytest

from src.weather_network import FIELDS,WeatherNetwork


def fixture():
    times=pd.to_datetime(['2025-01-01 00:00','2025-01-01 00:10','2025-01-01 00:20'])
    parts=[]
    for station,value in [('a',2.),('b',6.)]:
        q=pd.DataFrame({'station':station,'source_time':times})
        for field in FIELDS:q[field]=value
        parts.append(q)
    coords=pd.DataFrame({'lat':[35.,35.],'lon':[127.,127.02]},index=['a','b'])
    return pd.concat(parts),coords


def test_strict_time_and_renormalized_missing():
    source,coords=fixture()
    source.loc[source.station.eq('b')&source.source_time.eq(pd.Timestamp('2025-01-01 00:10')),'humidity']=np.nan
    clock=pd.to_datetime(['2025-01-01 00:00','2025-01-01 00:10','2025-01-01 00:20','2025-01-01 00:36'])
    current=pd.DataFrame({'aws_'+k:np.zeros(4) for k in FIELDS})
    x,m=WeatherNetwork(source,coords).build(clock,35.,127.01,current)
    assert np.isnan(x.loc[0,'network_air_temp_idw'])
    assert x.loc[1,'network_air_temp_idw']==pytest.approx(4.)
    assert x.loc[2,'network_humidity_idw']==2.
    assert x.loc[2,'network_humidity_count']==1.
    assert np.isnan(x.loc[3,'network_air_temp_idw'])
    assert m['strict_past'] and m['max_observation_age_minutes']==10.


def test_prefix_future_radius_and_no_source():
    source,coords=fixture();clock=pd.date_range('2025-01-01',periods=4,freq='10min')
    current=pd.DataFrame({'aws_'+k:np.zeros(4) for k in FIELDS})
    builder=WeatherNetwork(source,coords)
    full,_=builder.build(clock,35.,127.01,current)
    small,_=builder.build(clock[1:3],35.,127.01,current.iloc[1:3])
    pd.testing.assert_frame_equal(full.iloc[1:3].reset_index(drop=True),small,check_exact=True)
    changed=source.copy();changed.loc[changed.source_time>=clock[2],list(FIELDS)]=10000.
    p,_=WeatherNetwork(changed,coords).build(clock,35.,127.01,current)
    pd.testing.assert_frame_equal(p.iloc[:3],full.iloc[:3],check_exact=True)
    empty,m=builder.build(clock,0.,0.,current)
    assert empty.filter(like='_idw').isna().all().all() and m['candidates']==[]


def test_target_and_duplicate_rejection():
    source,coords=fixture()
    with pytest.raises(ValueError,match='targets'):WeatherNetwork(source.assign(ice=0),coords)
    with pytest.raises(ValueError,match='Unique'):WeatherNetwork(pd.concat([source,source.iloc[:1]]),coords)
