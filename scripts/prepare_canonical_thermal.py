"""원 기상 캐시와 다른 학습 입력을 별도 버전으로 정정한다. 기존 자료·실험은 보존한다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.thermal_weather_points import ThermalWeatherPoints
from src.segment_exposure import WeatherOnlySources
from src.temperature_transfer import THERMAL_FEATURES
from src.two_winter import validate
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation
from src.offline_runtime import deny_network


def main():
    private=ROOT/'outputs/private';out=private/'canonical_thermal_data_20261024_v1'
    if out.exists():raise FileExistsError('Preserve canonical thermal data')
    frozen=preservation();source=private/'extended_thermal_data_20261024_v1/development.parquet'
    receipt=json.loads((source.parent/'receipt.json').read_text('utf-8'))
    assert sha(source)==receipt['data_sha256']
    data=validate(pd.read_parquet(source)).sort_values(['station','time']).reset_index(drop=True)
    original=data.copy()
    metadata=private/'weather_network_review_20261010_v1/metadata_analysis/development_points.csv'
    coords=pd.read_csv(metadata,dtype={'station':str}).set_index('station')
    cache=private/'releases/20261007/outputs/private/point_sources'
    weather=WeatherOnlySources(pd.read_parquet(cache/'aws.parquet'),pd.read_parquet(cache/'asos.parquet'),
        pd.read_csv(cache/'weather_coordinates.csv',dtype={'station_id':str}))
    changes=[]
    with deny_network() as attempts:
        for (station,winter),part in data.groupby(['station','winter']):
            c=coords.loc[station]
            actual,_=ThermalWeatherPoints(weather,pd.DatetimeIndex(part.time)).build(c.lat,c.lon)
            for col in THERMAL_FEATURES:
                old=part[col].to_numpy(float);new=actual[col].to_numpy(float)
                mismatch=~np.isclose(old,new,rtol=0,atol=1e-10,equal_nan=True)
                for position in np.flatnonzero(mismatch):
                    changes.append(dict(station=station,winter=int(winter),time=str(part.iloc[position].time),
                        group=part.iloc[position].group,column=col,old=old[position],new=new[position]))
                # 반올림 차이뿐인 거리값은 유지하고 검출한 불일치만 바꾼다.
                index=part.index[mismatch];data.loc[index,col]=new[mismatch]
    pd.testing.assert_frame_equal(data[['station','time','group','ice','road_temp','winter']],original[['station','time','group','ice','road_temp','winter']])
    differences=pd.DataFrame(changes)
    assert set(differences.group)=={'competition'}, 'Outer evaluation inputs must be investigated separately'
    assert not attempts and preservation()==frozen
    out.mkdir();data.to_parquet(out/'development.parquet',index=False,compression='zstd')
    differences.to_csv(out/'input_corrections.csv',index=False)
    result=dict(status='canonical_thermal_inputs_prepared',rows=len(data),changed_values=len(differences),
        changed_rows=len(differences[['station','time']].drop_duplicates()),outer_validation_values_changed=0,
        explanation='Two-winter competition training core weather had different missing/invalid-air filtering from the common weather-only inference builder. Extra thermal inputs already matched. Source weather is now used consistently.',
        source_sha256=sha(source),data_sha256=sha(out/'development.parquet'),protected_labels_read=False,
        old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],network_attempts=0,
        source_signatures={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'src/thermal_weather_points.py',metadata,*[cache/n for n in ['aws.parquet','asos.parquet','weather_coordinates.csv']]]})
    (out/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='source_signatures'},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
