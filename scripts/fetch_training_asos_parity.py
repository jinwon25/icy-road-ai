"""기존 훈련 지역 ASOS만 같은 API로 받아 입력 형식 차이를 검증한다. 도로 정답은 요청하지 않는다."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, sys, time, requests, pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.kma_rwis_download import load_auth_key
from src.data_source import sha256_file as sha
from scripts.evaluate_synoptic_icing import read,write
from scripts.fetch_expanded_asos_inputs import parse_weather


def finish(out, plan, mapping, ids, records, frames):
    f=pd.concat(frames,ignore_index=True).sort_values(['STN','time']);assert not f.duplicated(['STN','time']).any()
    expected=sum((pd.Timestamp(b)-pd.Timestamp(a)).days*24+1 for a,b in plan['winters'])*len(ids)
    assert len(f)<=expected
    f.to_parquet(out/'asos_raw_fields.parquet',index=False,compression='zstd')
    write(out/'receipt.json',dict(status='training_asos_requests_complete',rows=len(f),expected_rows=expected,
        missing_hourly_rows=expected-len(f),stations=ids,requests=records,missing_rows_not_imputed=True,
        mapping_sha256=sha(mapping),data_sha256=sha(out/'asos_raw_fields.parquet'),code_sha256=sha(Path(__file__)),new_road_outcomes_read=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--recover-cached',action='store_true');args=parser.parse_args()
    plan=read(ROOT/'config/blind_icing_20261025.json');out=ROOT/plan['training_weather']
    mapping=ROOT/plan['mapping'];ids=sorted(pd.read_csv(mapping).asos_station.unique().tolist())
    if args.recover_cached:
        if (out/'receipt.json').exists():raise FileExistsError('Preserve completed receipt')
        records=read(out/'requests.json');assert len(records)==10 and all(r.get('http_status')==200 for r in records)
        frames=[]
        for r in records:
            p=r['parameters'];path=out/(p['tm1']+'.txt');assert sha(path)==r['sha256']
            frames.append(parse_weather(path.read_text('utf-8'),ids,pd.to_datetime(p['tm1'],format='%Y%m%d%H%M'),pd.to_datetime(p['tm2'],format='%Y%m%d%H%M')))
        finish(out,plan,mapping,ids,records,frames);return
    if out.exists():raise FileExistsError('Preserve weather parity acquisition')
    out.mkdir(parents=True)
    key=load_auth_key(ROOT/'secret.env');endpoint='https://apihub.kma.go.kr/api/typ01/url/kma_sfctm3.php'
    records=[];frames=[]
    for lo,hi in plan['winters']:
        edges=pd.date_range(lo,hi,freq='MS');windows=[(edges[0]-pd.Timedelta(hours=1),edges[0]-pd.Timedelta(hours=1))]
        windows += [(a,b-pd.Timedelta(hours=1)) for a,b in zip(edges[:-1],edges[1:])]
        for start,end in windows:
            params=dict(tm1=start.strftime('%Y%m%d%H%M'),tm2=end.strftime('%Y%m%d%H%M'),stn=':'.join(map(str,ids)),help='1')
            record=dict(endpoint=endpoint,parameters=params,at_utc=datetime.now(timezone.utc).isoformat())
            try:
                r=requests.get(endpoint,params=params|dict(authKey=key),timeout=(10,50),allow_redirects=False)
                if r.status_code!=200:raise ValueError('Unexpected status '+str(r.status_code))
                path=out/(params['tm1']+'.txt');path.write_text(r.text.replace(key,'[REDACTED]'),'utf-8')
                f=parse_weather(path.read_text('utf-8'),ids,start,end);frames.append(f)
                record.update(http_status=r.status_code,rows=len(f),sha256=sha(path))
            except (requests.RequestException,ValueError) as exc:
                record['error_type']=type(exc).__name__;records.append(record);write(out/'requests.json',records)
                raise RuntimeError('Weather acquisition incomplete; credential details suppressed') from None
            records.append(record);write(out/'requests.json',records);print(params['tm1'],len(f),flush=True);time.sleep(1.2)
    finish(out,plan,mapping,ids,records,frames)


if __name__=='__main__':main()
