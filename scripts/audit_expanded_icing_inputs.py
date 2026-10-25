"""추가 후보 위치·선택과 ASOS 원문의 모든 시각·지점·필드를 별도로 대조한다."""
import argparse
import math
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.validation import PROTECTED_STATIONS
from src.data_source import sha256_file as sha
from scripts.evaluate_synoptic_icing import read,write
from scripts.evaluate_method_blending import preservation


def km(a,b):
    lat1,lon1,lat2,lon2=map(math.radians,[a.lat,a.lon,b.lat,b.lon])
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 12742.0176*math.atan2(math.sqrt(h),math.sqrt(max(0,1-h)))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['screen','weather','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if out.exists() or not out.is_relative_to((ROOT/'outputs/private').resolve()):raise ValueError('New private output required')
    frozen=preservation();sr=read(a.screen/'receipt.json');wr=read(a.weather/'receipt.json');plan=read(ROOT/'config/expanded_icing_validation_20261025.json')
    assert wr['status']=='weather_inputs_complete' and wr['screen_receipt_sha256']==sha(a.screen/'receipt.json')
    assert sr['screen_sha256']==sha(a.screen/'screen.csv')
    for name,digest in sr['source_signatures'].items():assert sha(ROOT/name)==digest
    used=set(PROTECTED_STATIONS)
    for name,digest in read(a.screen/'request_manifest_signatures.json').items():
        assert sha(ROOT/name)==digest
        for record in read(ROOT/name).get('records',{}).values():
            if isinstance(record,dict) and 'station' in record:used.add(str(record['station']))
    roads=pd.read_csv(ROOT/plan['road_catalog'],dtype={'station':str})
    expected=roads.loc[roads.independent_station_candidate&roads.target_route_candidate&~roads.already_in_competition_scope&~roads.station.isin(used)]
    screen=pd.read_csv(a.screen/'screen.csv',dtype={'station':str},float_precision='round_trip')
    assert set(expected.station)==set(screen.station)
    known=roads.loc[roads.station.isin(used)|roads.already_in_competition_scope]
    history=pd.read_csv(ROOT/plan['history'],encoding='cp949')
    start=pd.to_datetime(history['시작일']);end=pd.to_datetime(history['종료일'])
    good=history.loc[start.le('2024-11-01')&(end.isna()|end.ge('2026-03-01'))].rename(columns={'지점':'station','위도':'lat','경도':'lon'})
    good=good.dropna(subset=['lat','lon']);good=good.loc[~good.station.duplicated(keep=False)].sort_values('station')
    assert len(good)==sr['usable_asos_locations']
    for row in screen.itertuples():
        pairs=sorted((km(row,w),w.station) for w in good.itertuples())
        assert pairs[0][1]==row.asos_station
        np.testing.assert_allclose([pairs[0][0],min(km(row,k) for k in known.itertuples())],[row.asos_distance_km,row.known_road_min_km],atol=1e-9,rtol=0)
        assert row.eligible==(row.asos_distance_km<=plan['maximum_asos_km'] and row.known_road_min_km>=plan['minimum_known_road_km'])
    chosen=[]
    for row in screen.loc[screen.eligible].sort_values(['known_road_min_km','asos_distance_km','station'],ascending=[False,True,True]).itertuples():
        if any(km(row,k)<plan['minimum_selected_separation_km'] for k in chosen):continue
        chosen.append(row)
        if len(chosen)==plan['maximum_selected']:break
    assert [r.station for r in chosen]==sr['selected_stations']
    f=pd.read_parquet(a.weather/'asos_raw_fields.parquet');all_rows=[]
    for rec in wr['requests']:
        stamp=rec['parameters']['tm1'];path=a.weather/(stamp+'.txt');assert sha(path)==rec['sha256']
        lines=path.read_text('utf-8').splitlines()
        rows=[line.split() for line in lines if line.strip() and not line.lstrip().startswith('#')]
        assert len(rows)==rec['observation_rows'] and all(len(r)==46 for r in rows)
        for row in rows:
            assert row[1] in set(map(str,wr['stations']))
            assert rec['parameters']['tm1']<=row[0]<=rec['parameters']['tm2']
        all_rows.extend(rows)
    rows=sorted(all_rows,key=lambda r:(r[1],r[0]));saved=f.sort_values(['STN','TM']).reset_index(drop=True)
    np.testing.assert_array_equal(np.asarray(rows),saved.drop(columns='time').to_numpy())
    assert not saved.duplicated(['STN','TM']).any()
    expected_times=[]
    for lo,hi in plan['winters']:
        expected_times+=pd.date_range(pd.Timestamp(lo)-pd.Timedelta(hours=1),pd.Timestamp(hi)-pd.Timedelta(hours=1),freq='h').tolist()
    for station,part in saved.groupby('STN'):
        assert pd.to_datetime(part.TM,format='%Y%m%d%H%M').tolist()==expected_times
    assert len(saved)==wr['expected_rows']==23048 and preservation()==frozen
    out.mkdir(parents=True)
    receipt=dict(status='expanded_input_acquisition_independently_verified',candidate_locations_checked=len(screen),
        weather_locations_checked=len(good),selected_stations=sr['selected_stations'],weather_rows_checked=len(saved),raw_fields_checked=len(saved)*46,
        screen_receipt_sha256=sha(a.screen/'receipt.json'),weather_receipt_sha256=sha(a.weather/'receipt.json'),
        code_sha256=sha(Path(__file__)),road_outcomes_read=False,independent_performance_test_completed=False,frozen_counts=list(frozen))
    write(out/'receipt.json',receipt);print(receipt,flush=True)


if __name__=='__main__':main()
