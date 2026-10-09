"""새 위치 추론에 필요한 원천을 정답과 분리해 캐시한다. RWIS는 개발 지점만 저장한다."""
import json
import sys
import zipfile
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import competition_archive,sha256_file
from src.weather_features import _load_aws,_load_daily,_numeric_range
from src.physical_features import load_thermal_sources
from src.validation import canonical_station_id,assert_training_stations
from scripts.audit_ice_weather_history import source_history,HISTORY
from scripts.build_physical_features import ASOS_FIELDS


def main():
    private=ROOT/'outputs/private';archive=competition_archive(ROOT)
    with zipfile.ZipFile(archive) as z:
        aws=_load_aws(z,None)
        columns=['시간','지점','기온(°C)',*ASOS_FIELDS]
        names=['source_time','station','air_temp',*[v[0].removeprefix('asos_') for v in ASOS_FIELDS.values()]]
        asos=_load_daily(z,'ASOS',columns,names,None)
    for col,low,high in [('air_temp',-60,70),('humidity',0,100),('wind_speed',0,75),('rain_15m',0,500),('dewpoint',-80,60)]:
        _numeric_range(aws,col,low,high)
    history=source_history(aws)
    memory=pd.read_parquet(private/'moisture_memory/aws_history.parquet')
    aws=aws.merge(history,on=['station','source_time'],validate='one_to_one').merge(memory,on=['station','source_time'],validate='one_to_one')
    asos['source_time']=pd.to_datetime(asos.source_time)
    asos['station']=asos.station.map(canonical_station_id)
    _numeric_range(asos,'air_temp',-60,70)
    for name,low,high in ASOS_FIELDS.values():_numeric_range(asos,name.removeprefix('asos_'),low,high)
    rwis=load_thermal_sources(archive)
    assert_training_stations(rwis.station.unique())
    if 'ice' in rwis or 'state_raw' in rwis:raise AssertionError('State labels in inference sources')
    out=private/'point_sources';out.mkdir(parents=True,exist_ok=True)
    aws.to_parquet(out/'aws.parquet',index=False,compression='zstd');asos.to_parquet(out/'asos.parquet',index=False,compression='zstd')
    rwis.to_parquet(out/'rwis.parquet',index=False,compression='zstd')
    inventory=pd.read_csv(private/'full/station_inventory.csv',dtype={'station_id':str})
    inventory=inventory.loc[inventory.kind.isin(['AWS','ASOS']),['kind','station_id','latitudes','longitudes']]
    inventory.to_csv(out/'weather_coordinates.csv',index=False,encoding='utf-8-sig')
    summary={'archive_sha256':sha256_file(archive),'rows':{'aws':len(aws),'asos':len(asos),'rwis':len(rwis)},'rwis_stations':sorted(rwis.station.unique()),
             'source_files':{f.name:sha256_file(f) for f in out.glob('*.parquet')},
             'rule':'RWIS development only; protected sources and road-state labels excluded. Raw road temperature is reference input, not target history.'}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
