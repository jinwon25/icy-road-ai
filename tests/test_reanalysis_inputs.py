import numpy as np
import pandas as pd
import pytest
from src.reanalysis_inputs import FIELDS,parse_response,histories


def payload():
    return dict(timezone='Asia/Seoul',utc_offset_seconds=32400,latitude=35.,longitude=127.,elevation=100.,
        hourly_units={k:v[0] for k,v in FIELDS.items()},
        hourly={'time':pd.date_range('2024-11-01',periods=24,freq='h').strftime('%Y-%m-%dT%H:%M').tolist(),
                **{k:[.5]*24 for k in FIELDS}})


def parse(p):return parse_response(p,'train',35.,127.,'2024-11-01','2024-11-01')


@pytest.mark.parametrize('change',['units','timezone','grid','duplicate','field'])
def test_reanalysis_rejects_silent_conversion_and_misalignment(change):
    p=payload()
    if change=='units':p['hourly_units']['temperature_2m']='K'
    if change=='timezone':p['utc_offset_seconds']=0
    if change=='grid':p['latitude']=36.
    if change=='duplicate':p['hourly']['time'][1]=p['hourly']['time'][0]
    if change=='field':p['hourly']['road_temp']=[0.]*24
    with pytest.raises(ValueError):parse(p)


def test_reanalysis_preserves_minus_temperature_but_masks_invalid_moisture():
    p=payload();p['hourly']['temperature_2m'][0]=-9.;p['hourly']['soil_moisture_0_to_7cm'][0]=-9.
    f,q=parse(p)
    assert f.temperature_2m.iloc[0]==-9.
    assert np.isnan(f.soil_moisture_0_to_7cm.iloc[0])
    assert q['invalid_values']['soil_moisture_0_to_7cm']==1
    assert q['hours']==24


def test_reanalysis_histories_use_only_prior_rows_and_reset_after_gap():
    f,_=parse(payload());a=histories(f)
    f.loc[12:,'temperature_2m']=99.
    pd.testing.assert_frame_equal(a.iloc[:12],histories(f).iloc[:12])
    gap=pd.concat([f.iloc[:12],f.iloc[15:]],ignore_index=True)
    assert np.isnan(histories(gap).temperature_2m_mean6h.iloc[12])
    f['ice']=0
    with pytest.raises(ValueError):histories(f)


def test_reanalysis_model_has_only_predeclared_added_inputs():
    from src.reanalysis_models import added_columns,feature_table
    f=pd.DataFrame({c:[1.,2.] for c in added_columns('era5_memory')})
    base=pd.DataFrame({f'base_{i}':[0.,1.] for i in range(63)})
    f['ice']=[0,1];f['road_temp']=[-100.,100.];f['station']=['unseen','unseen']
    raw=feature_table(f,'era5_raw',base);memory=feature_table(f,'era5_memory',base)
    assert raw.shape==(2,71) and memory.shape==(2,83)
    assert not {'ice','road_temp','station'}&set(memory)
    f.ice=1-f.ice;f.road_temp=0
    pd.testing.assert_frame_equal(raw,feature_table(f,'era5_raw',base))
    with pytest.raises(ValueError):feature_table(f,'era5_raw',base.iloc[::-1])


def test_reanalysis_icing_selection_uses_declared_simple_tie_rule():
    from scripts.evaluate_reanalysis_icing import choose
    rows=[dict(candidate='asos_zero',complexity=0,mean_f1=.1,fp=100,threshold=.5),
          dict(candidate='era5_raw',complexity=2,mean_f1=.1+5e-13,fp=1,threshold=.8)]
    assert choose(rows,'mean_f1')['candidate']=='asos_zero'
    rows[1]['mean_f1']=.11
    assert choose(rows,'mean_f1')['candidate']=='era5_raw'
