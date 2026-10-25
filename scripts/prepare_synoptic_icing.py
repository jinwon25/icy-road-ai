"""제공본의 미사용 ASOS 관측 8개를 과거 60분 규칙으로 결합하고 원천과 별도 대조한다."""
import argparse,json,zipfile
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.observation_io import daily_members,read_columns,numeric_observations
from src.data_source import competition_archive,sha256_file as sha
from src.weather_features import prior_join
from src.thermal_weather_points import strictly_prior_values
from src.two_winter import validate
from scripts.evaluate_method_blending import preservation

FIELDS={'이슬점온도(°C)':'dewpoint_obs','증기압(hPa)':'vapor_pressure','현지기압(hPa)':'pressure',
        '풍속(m/s)':'wind_speed','시정(10m)':'visibility','중하층운량(10분위)':'low_cloud',
        '3시간신적설(cm)':'new_snow3h','5cm 지중온도(°C)':'soil5cm'}
BOUNDS={'dewpoint_obs':(-80,50),'vapor_pressure':(0,100),'pressure':(500,1100),'wind_speed':(0,100),
        'visibility':(0,10000),'low_cloud':(0,10),'new_snow3h':(0,500),'soil5cm':(-60,80)}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to((ROOT/'outputs/private').resolve()):raise ValueError('New private output required')
    frozen=preservation();source=ROOT/'outputs/private/solar_memory_data_20261024_v1/development.parquet'
    assert sha(source)==json.loads((source.parent/'receipt.json').read_text('utf-8'))['data_sha256']
    data=validate(pd.read_parquet(source)).sort_values(['station','time']).reset_index(drop=True)
    mapping_path=source.parent/'station_solar_coordinates.csv'
    mapping=pd.read_csv(mapping_path,dtype={'station':str,'asos_station':str}).set_index('station').asos_station
    archive=competition_archive(ROOT/'outputs/private/releases/20261007')
    frames=[];members=[]
    with zipfile.ZipFile(archive) as z:
        for name in daily_members(z,'ASOS'):
            # ASOS만 열며 RWIS·보호 지점의 관측 파일은 열지 않는다.
            frames.append(read_columns(z,name,['시간','지점',*FIELDS],['source_time','station',*FIELDS.values()]))
            members.append(name)
    raw=pd.concat(frames,ignore_index=True);raw.station=raw.station.str.replace(r'\.0$','',regex=True)
    raw.source_time=pd.to_datetime(raw.source_time)
    assert not raw.duplicated(['station','source_time']).any() and raw.source_time.dt.tz is None
    invalid={}
    for col,(lo,hi) in BOUNDS.items():
        values=numeric_observations(raw[col]);invalid[col]=int((values.notna()&~values.between(lo,hi)).sum())
        raw[col]=values.where(values.between(lo,hi))
    columns=list(FIELDS.values());joined=[];checked=0
    for station,part in data.groupby('station',sort=True):
        s=raw.loc[raw.station.eq(mapping[station]),['source_time',*columns]].sort_values('source_time')
        result=prior_join(part[['station','time']],s,'asos',60)
        expected=strictly_prior_values(pd.DatetimeIndex(part.time),s,columns)
        np.testing.assert_allclose(result[['asos_'+c for c in columns]],expected,atol=0,rtol=0,equal_nan=True)
        checked+=expected.size;joined.append(result)
    values=pd.concat(joined,ignore_index=True)
    merged=data.merge(values,on=['station','time'],how='left',validate='one_to_one',suffixes=('','_raw'))
    # 기존 입력은 변경하지 않으며 새 자료의 관측 시각도 따로 보존한다.
    pd.testing.assert_frame_equal(merged[data.columns],data,check_exact=True)
    assert not np.isinf(merged[['asos_'+c for c in columns]].to_numpy(float)).any()
    out.mkdir(parents=True);merged.to_parquet(out/'development.parquet',index=False,compression='zstd')
    raw.to_parquet(out/'asos_extra_source.parquet',index=False,compression='zstd')
    merged.groupby(['station','winter'])[['asos_'+c for c in columns]].count().to_csv(out/'availability.csv')
    assert preservation()==frozen
    result=dict(status='synoptic_icing_inputs_verified',rows=len(merged),added_features=columns,checked_values=checked,
        source_members=len(members),source_kind='provided_ASOS_unused_columns',external_data_downloaded=False,
        protected_labels_read=False,original_input_changed=False,invalid_out_of_range=invalid,
        source_sha256=sha(source),archive_sha256=sha(archive),mapping_sha256=sha(mapping_path),
        data_sha256=sha(out/'development.parquet'),raw_sha256=sha(out/'asos_extra_source.parquet'),
        script_sha256=sha(Path(__file__)),frozen_counts=list(frozen))
    (out/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
