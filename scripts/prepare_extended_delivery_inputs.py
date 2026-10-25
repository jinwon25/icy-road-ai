"""v2 예측 위치의 기상만 확장하고 기존 결빙 입력과 일치함을 검산한다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.thermal_weather_points import ThermalWeatherPoints
from src.segment_exposure import WeatherOnlySources
from src.submission_runtime import FEATURES,WATER
from src.thermal_runtime import EXTRA,thermal_predictors
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation


def main():
    private=ROOT/'outputs/private';out=private/'extended_delivery_inputs_20261024_v2'
    if out.exists():raise FileExistsError('Preserve completed delivery input preparation')
    source=private/'submission_candidate_20261024_v2';manifest=json.loads((source/'manifest.json').read_text('utf-8'))
    groups_path=source/'data/prediction_group_manifest.json';index_path=source/'data/point_prediction_index.csv'
    for path in [groups_path,index_path]:assert sha(path)==manifest['files'][path.relative_to(source).as_posix()]['sha256']
    groups=json.loads(groups_path.read_text('utf-8'));index=pd.read_csv(index_path,dtype={'id':str,'prediction_group':str,'winter':str})
    cache=private/'releases/20261007/outputs/private/point_sources'
    weather=WeatherOnlySources(pd.read_parquet(cache/'aws.parquet'),pd.read_parquet(cache/'asos.parquet'),
        pd.read_csv(cache/'weather_coordinates.csv',dtype={'station_id':str}))
    frozen=preservation();builders={};receipts={};values=0;rows=0;history_missing=0
    out.mkdir();(out/'weather_groups').mkdir()
    with deny_network() as attempts:
        for group,metadata in groups.items():
            original_path=source/'data/weather_groups'/(group+'.parquet')
            assert sha(original_path)==metadata['weather_sha256']
            original=pd.read_parquet(original_path)
            point=index.loc[index.prediction_group.eq(group)].iloc[0]
            winter=str(metadata['winter'])
            if winter not in builders:builders[winter]=ThermalWeatherPoints(weather,pd.DatetimeIndex(original.time))
            actual,mapping=builders[winter].build(point.point_lat,point.point_lon)
            assert [p['station'] for p in mapping['aws_candidates']]==metadata['aws_candidates']
            assert mapping['asos_station']==metadata['asos_station']
            core=list(dict.fromkeys([*FEATURES,*WATER]))
            np.testing.assert_allclose(actual[core],original[core],rtol=0,atol=1e-10,equal_nan=True)
            pd.testing.assert_series_equal(actual.time.reset_index(drop=True),original.time.reset_index(drop=True))
            # 기존 핵심 입력 바이트값을 그대로 사용해 결빙 판정 보존을 보장한다.
            extended=original.copy()
            for column in EXTRA:
                if column not in extended:extended[column]=actual[column].to_numpy()
            x,valid,_=thermal_predictors(extended,'thermal_history')
            history_missing+=int(x.isna().any(axis=1).sum())
            path=out/'weather_groups'/(group+'.parquet');extended.to_parquet(path,index=False,compression='zstd')
            receipts[group]=dict(winter=winter,rows=len(extended),weather_sha256=sha(path),
                original_weather_sha256=metadata['weather_sha256'],temperature_valid_rows=int(valid.sum()),
                aws_candidates=metadata['aws_candidates'],asos_station=metadata['asos_station'])
            rows+=len(extended);values+=len(extended)*len(core)
            if len(receipts)%20==0:print('thermal delivery inputs',len(receipts),'/',len(groups),flush=True)
    assert not attempts and preservation()==frozen and len(receipts)==138
    result=dict(status='extended_weather_inputs_verified',group_count=len(receipts),rows=rows,
        core_values_compared=values,core_input_changes=0,rows_with_any_missing_predictor=history_missing,
        protected_labels_read=False,network_attempts=0,old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],
        source_manifest_sha256=sha(source/'manifest.json'),groups=receipts,
        source_signatures={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'src/thermal_weather_points.py',ROOT/'src/thermal_runtime.py',
            *[cache/n for n in ['aws.parquet','asos.parquet','weather_coordinates.csv']]]})
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print({k:v for k,v in result.items() if k not in ['groups','source_signatures']},flush=True)

if __name__=='__main__':main()
