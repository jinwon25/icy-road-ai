"""구간 추론에 추가로 필요한 ASOS 172만 같은 공식 원문 형식으로 확보한다."""
from datetime import datetime,timezone
import argparse
from pathlib import Path
import sys
import time

import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.kma_rwis_download import load_auth_key
from src.data_source import sha256_file as sha
from scripts.fetch_expanded_asos_inputs import parse_weather
from scripts.evaluate_objective_icing import read,write


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/private/weather_mapping_asos_20261031_v1')
    out=parser.parse_args().output.resolve()
    if not out.is_relative_to((ROOT/'outputs/private').resolve()):raise ValueError('Private output required')
    if out.exists():raise FileExistsError('Preserve mapping weather source')
    references=ROOT/'outputs/private/segment_exposure_20261009_v1/point_references.json'
    needed={str(r['asos_station']) for r in read(references)}
    current=ROOT/'outputs/private/asos_training_parity_20261025_v1/asos_raw_fields.parquet'
    supplied=set(pd.read_parquet(current,columns=['STN']).STN.astype(str))
    missing=sorted(needed-supplied);assert missing==['172']
    out.mkdir(parents=True);windows=[]
    for year in [2024,2025]:
        edges=pd.date_range(f'{year}-11-01',f'{year+1}-03-01',freq='MS')
        windows.append((edges[0]-pd.Timedelta(hours=1),edges[0]-pd.Timedelta(hours=1)))
        windows.extend((a,b-pd.Timedelta(hours=1)) for a,b in zip(edges[:-1],edges[1:]))
    write(out/'plan.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),stations=missing,
        windows=[(str(a),str(b)) for a,b in windows],reason='same official ASOS format for all seven source stations selected by segment geometry',
        references_sha256=sha(references),existing_weather_sha256=sha(current),source_sha256=sha(Path(__file__)),
        road_observations_requested=False))
    key=load_auth_key(ROOT/'secret.env');endpoint='https://apihub.kma.go.kr/api/typ01/url/kma_sfctm3.php'
    records=[];frames=[]
    for start,end in windows:
        params=dict(tm1=start.strftime('%Y%m%d%H%M'),tm2=end.strftime('%Y%m%d%H%M'),stn='172',help='1')
        record=dict(endpoint=endpoint,parameters=params,at_utc=datetime.now(timezone.utc).isoformat())
        try:
            response=requests.get(endpoint,params=params|dict(authKey=key),timeout=(10,45),allow_redirects=False)
            record['http_status']=response.status_code
            path=out/(params['tm1']+'.txt');path.write_text(response.text.replace(key,'[REDACTED]'),encoding='utf-8')
            record['sha256']=sha(path)
            if response.status_code==200:
                frame=parse_weather(path.read_text(encoding='utf-8'),missing,start,end)
                frames.append(frame);record['rows']=len(frame)
        except (requests.RequestException,ValueError) as exc:record['error_type']=type(exc).__name__
        records.append(record);write(out/f'request_{len(records):02d}.json',record)
        print(params['tm1'],record.get('http_status'),record.get('rows'),flush=True)
        if 'rows' not in record:break
        time.sleep(1.2)
    successful=len(records)==len(windows) and all('rows' in r for r in records)
    if frames:
        combined=pd.concat(frames,ignore_index=True).sort_values(['STN','time'])
        assert not combined.duplicated(['STN','time']).any()
        combined.to_parquet(out/'asos_raw_fields.parquet',index=False,compression='zstd')
    expected=sum(int((b-a)/pd.Timedelta(hours=1))+1 for a,b in windows)
    write(out/'receipt.json',dict(status='mapping_asos_requests_complete' if successful else 'mapping_asos_requests_incomplete',
        expected_rows=expected,received_rows=sum(r.get('rows',0) for r in records),requests=records,
        missing_rows_imputed=False,credentials_stored=False,road_observations_requested=False,
        data_sha256=sha(out/'asos_raw_fields.parquet') if frames else None))


if __name__=='__main__':main()
