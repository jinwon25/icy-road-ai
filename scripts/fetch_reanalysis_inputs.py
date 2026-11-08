"""기존 개발 지점의 공개 ERA5-Land 입력만 확보하고 재시도 가능한 원문 영수증을 남긴다."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time

import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.reanalysis_inputs import FIELDS,parse_response


def read(path):return json.loads(path.read_text(encoding='utf8'))


def write(path,value):
    text=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(text,encoding='utf8');temporary.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--limit',type=int)
    args=parser.parse_args();config=ROOT/'config/reanalysis_inputs_20261031.json';plan=read(config)
    out=ROOT/plan['output'];out.mkdir(parents=True,exist_ok=True)
    coordinates=ROOT/plan['coordinates'];allowed_source=ROOT/plan['allowed_station_source']
    allowed=set(pd.read_parquet(allowed_source,columns=['station']).station)
    assert len(allowed)==23 and not allowed&set(plan['blocked_stations'])
    points=pd.read_csv(coordinates,dtype={'station':str})[['station','lat','lon']].sort_values('station')
    assert set(points.station)==allowed and not points.station.duplicated().any()
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [config,coordinates,allowed_source,Path(__file__),ROOT/'src/reanalysis_inputs.py']}
    if (out/'plan.json').exists():
        saved=read(out/'plan.json');assert saved['signatures']==signatures
    else:
        write(out/'plan.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),settings=plan,signatures=signatures,
            requested_sites=points.to_dict('records'),new_outcomes_requested=False))
    manifest_path=out/'request_manifest.json'
    manifest=read(manifest_path) if manifest_path.exists() else dict(records={},status='collecting')
    frames=[];count=0;last_call=0.;session=requests.Session()
    for row in points.itertuples(index=False):
        for start,end in plan['periods']:
            identifier=row.station+'_'+start[:4];path=out/(identifier+'.json')
            params=dict(latitude=row.lat,longitude=row.lon,start_date=start,end_date=end,
                hourly=','.join(plan['hourly']),models=plan['model'],timezone=plan['timezone'],
                elevation=plan['elevation'],cell_selection=plan['cell_selection'])
            if identifier in manifest['records']:
                assert sha(path)==manifest['records'][identifier]['sha256'];payload=read(path)
            else:
                if args.limit is not None and count>=args.limit:
                    print('LIMIT reached; original requests preserved',flush=True);return
                if path.exists():raise FileExistsError('Unrecorded response requires inspection')
                for attempt in range(3):
                    time.sleep(max(0,plan['minimum_request_interval_seconds']-(time.monotonic()-last_call)))
                    last_call=time.monotonic()
                    try:response=session.get(plan['endpoint'],params=params,timeout=(10,60))
                    except requests.RequestException as error:
                        if attempt==2:raise RuntimeError(type(error).__name__+' while collecting public ERA5-Land') from None
                        time.sleep(2**attempt);continue
                    if response.status_code in [429,500,502,503,504] and attempt<2:
                        time.sleep(min(60,max(2**attempt,float(response.headers.get('Retry-After','2')))));continue
                    response.raise_for_status();payload=response.json();break
                frame,quality=parse_response(payload,row.station,row.lat,row.lon,start,end,plan['maximum_grid_distance_km'])
                assert min(quality['valid_fractions'].values())>=plan['minimum_valid_fraction'],quality
                write(path,payload)
                manifest['records'][identifier]=dict(at_utc=datetime.now(timezone.utc).isoformat(),params=params,
                    endpoint=plan['endpoint'],sha256=sha(path),bytes=path.stat().st_size,quality=quality)
                write(manifest_path,manifest);count+=1
                print('FETCH',len(manifest['records']),'/46',identifier,quality['hours'],'hours',flush=True)
            frame,quality=parse_response(payload,row.station,row.lat,row.lon,start,end,plan['maximum_grid_distance_km'])
            frames.append(frame)
    result=pd.concat(frames,ignore_index=True).sort_values(['station','source_time']).reset_index(drop=True)
    assert len(manifest['records'])==46 and not result.duplicated(['station','source_time']).any()
    if not (out/'hourly.parquet').exists():result.to_parquet(out/'hourly.parquet',index=False,compression='zstd')
    else:pd.testing.assert_frame_equal(pd.read_parquet(out/'hourly.parquet'),result)
    manifest.update(status='complete',rows=len(result),variables=list(FIELDS),hourly_sha256=sha(out/'hourly.parquet'),
        retrospective_only=True,grid_is_not_road_surface=True,new_outcomes_requested=False)
    write(manifest_path,manifest)
    (out/'ATTRIBUTION.txt').write_text(plan['attribution']+'\n'+plan['scope']+'\n',encoding='utf8')
    print('COMPLETE',len(result),'hourly rows',flush=True)


if __name__=='__main__':main()
