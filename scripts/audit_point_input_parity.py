"""새 위치 입력기의 모든 개발 행·수치 특성을 기존 검증 입력과 대조한다."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.point_inputs import PointInputBuilder
from src.physical_features import ThermalContext,CONTEXT_FEATURES
from src.moisture_memory import MEMORY_FEATURES
from scripts.baseline_ice_logistic import FEATURES


def main():
    private=ROOT/'outputs/private'
    expected=pd.read_parquet(private/'moisture_memory/features.parquet')
    physical=json.loads((private/'physical_features/summary.json').read_text(encoding='utf-8'))
    columns=FEATURES+[c for c in physical['additional_features'] if c!='elevation_m']+MEMORY_FEATURES+CONTEXT_FEATURES
    meta=pd.read_csv(private/'sensor_availability/metadata.csv',dtype={'station':str})
    meta=meta.loc[meta.kind.eq('RWIS'),['station','route','lat','lon']]
    builder=PointInputBuilder.from_root(ROOT)
    thermal=ThermalContext(expected,pd.read_parquet(private/'point_sources/rwis.parquet'),meta)
    baseline=pd.read_parquet(private/'neighbor_transfer/predictions.parquet')
    baseline=baseline.loc[baseline.delay_minutes.eq(0)]
    rows=[]
    for point in meta.to_dict(orient='records'):
        sid=point['station'];target=expected.loc[expected.station.eq(sid)].sort_values('time').copy()
        context,_=thermal.features(target,{sid})
        reference=pd.concat([target,context],axis=1).reset_index(drop=True)
        actual,mapping=builder.build(point,target.time,{sid})
        pd.testing.assert_series_equal(reference.time,actual.time,check_names=False)
        a,b=reference[columns].to_numpy(dtype=float),actual[columns].to_numpy(dtype=float)
        np.testing.assert_allclose(a,b,rtol=1e-12,atol=1e-12,equal_nan=True)
        paired=baseline.loc[baseline.station.eq(sid),['time','neighbor_road_temp']].merge(actual[['time','neighbor_road_temp']],on='time',suffixes=('_reference','_new'),validate='one_to_one')
        np.testing.assert_allclose(paired.neighbor_road_temp_reference,paired.neighbor_road_temp_new,atol=1e-12,equal_nan=True)
        rows.append({'station':sid,'rows':len(actual),'feature_count':len(columns),'temperature_neighbor_rows':len(paired),'mapping':mapping})
        print(sid,'parity',len(actual),flush=True)
    out=private/'point_sources'
    summary={'status':'all_development_point_inputs_equal','rows':sum(r['rows'] for r in rows),'feature_count':len(columns),'stations':len(rows),'checks':rows,
             'meaning':'New-location input generator matches all development numeric features and zero-delay temperature neighbor inputs, at1e-12 tolerance.'}
    (out/'parity_verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['status','rows','feature_count','stations']}),flush=True)


if __name__=='__main__':main()
