"""봉인 범위 그대로 재개한다. 긴 요청 실패를 줄이고 전체 요청 간격은 1.2초로 유지한다."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import threading
import time
import sys
import requests
import pandas as pd
import hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.blind_icing_validation import DEFAULT,read,write,verify,transport_plans,now
from src.kma_rwis_download import daily_requests,load_auth_key,parse_observations,exact_ten_minute_grid,RwisResponseError
from src.kma_rwis_transport import ValidatedRoadClient
from src.data_source import sha256_file as sha
from scripts.fresh_station_validation import old_freezes
from src.rwis_response_quality import quarantine_duplicates


class GlobalThrottle:
    def __init__(self,interval,log):
        self.lock=threading.Lock();self.last=0.;self.interval=interval;self.log=log

    def wait(self,params):
        import json
        with self.lock:
            # Windows 타이머의 단일 sleep 오차를 실제 경과시간 재확인으로 막는다.
            while time.monotonic()-self.last<self.interval:
                time.sleep(max(.02,self.interval-(time.monotonic()-self.last)+.02))
            self.last=time.monotonic()
            record=dict(at_utc=now(),monotonic=self.last,scheduler_version=2,station=str(params['var']),start=params['tm1'],end=params['tm2'])
            with self.log.open('a',encoding='utf-8') as stream:stream.write(json.dumps(record)+'\n')


class LimitedSession:
    def __init__(self,throttle):self.session=requests.Session();self.throttle=throttle
    def get(self,url,**kwargs):
        self.throttle.wait(kwargs['params'])
        response=self.session.get(url,**kwargs)
        if response.status_code==200:
            body=response.text;params=kwargs['params']
            if params['authKey'] in body:raise ValueError('Response echoes credential; suppressed')
            try:
                parse_observations(body,params['var'],pd.to_datetime(params['tm1'],format='%Y%m%d%H%M'),pd.to_datetime(params['tm2'],format='%Y%m%d%H%M'))
            except RwisResponseError as exc:
                if str(exc)!='Duplicate station/time returned':raise
            clean,report=quarantine_duplicates(body,params['var'])
            if report['identical_duplicate_rows_removed'] or report['conflicting_keys']:
                out=DEFAULT/'response_quality';out.mkdir(exist_ok=True)
                stem=f"{params['var']}_{params['tm1']}_{params['tm2']}"
                raw=out/(stem+'_original.txt');receipt=out/(stem+'.json')
                if raw.exists():assert raw.read_text('utf-8')==body.replace('\r\n','\n')
                else:raw.write_text(body,'utf-8')
                write(receipt,dict(at_utc=now(),raw_path=raw.relative_to(DEFAULT).as_posix(),raw_sha256=sha(raw),report=report,
                    canonical_text_sha256=hashlib.sha256(clean.replace('\r\n','\n').encode()).hexdigest(),rule='all conflicting keys quarantined without target-dependent choice'))
                response._content=clean.encode('utf-8');response.encoding='utf-8'
        return response


class QualityRoadClient(ValidatedRoadClient):
    def _record(self,path,station,start,end,frame,reused):
        r=super()._record(path,station,start,end,frame,reused)
        p=DEFAULT/'response_quality'/f'{station}_{start:%Y%m%d%H%M}_{end:%Y%m%d%H%M}.json'
        if p.exists():r.update(quality_receipt=p.relative_to(DEFAULT).as_posix(),quality_receipt_sha256=sha(p))
        return r


def atomic_write(path,value):
    tmp=path.with_suffix('.json.tmp');write(tmp,value)
    for attempt in range(10):
        try:
            tmp.replace(path);return
        except PermissionError:
            if attempt==9:raise
            time.sleep(.05*(attempt+1))


def main():
    out=DEFAULT;seal=verify(out);plan=read(out/'plan.json');mp=out/'download_manifest.json';manifest=read(mp)
    assert read(out/'prediction_audit.json')['status']=='passed' and manifest['first_request_utc']>seal['sealed_at_utc']
    if manifest.get('status')=='complete':raise FileExistsError('Collection already complete')
    assert not (out/'summary.json').exists(), 'No collection changes after outcome evaluation'
    amendment=out/'transport_amendment_v4.json'
    if not amendment.exists():
        write(amendment,dict(at_utc=now(),reason='Apply recorded pre-analysis duplicate-conflict quarantine; preserve original responses and common missing-label mask. Predictions and evaluation code unchanged.',
            existing_daily_windows=len(manifest['records']),station_33402_maximum_chunk_minutes=360,other_station_chunk_minutes=1440,
            workers=4,global_minimum_seconds=1.2,changed_scope_dates_candidates_predictions_metrics=False,
            outcomes_analyzed_before_change=False,code_sha256=sha(Path(__file__)),seal_sha256=sha(out/'prediction_seal.json')))
    assert read(amendment)['code_sha256']==sha(Path(__file__))
    key=load_auth_key(ROOT/'secret.env');throttle=GlobalThrottle(1.2,out/'global_request_timing.jsonl');jobs=[]
    for p in transport_plans(plan):
        for station,start,end in daily_requests(p,p['development_start_kst'],p['development_end_kst'],window_minutes=p['window_minutes']):
            identifier=f'{station}_{start:%Y%m%d%H%M}';path=out/'observations'/(identifier+'.parquet')
            if identifier in manifest['records']:
                assert sha(path)==manifest['records'][identifier]['sha256'];continue
            if path.exists():raise FileExistsError('Unrecorded observation evidence; inspect without replacing')
            jobs.append((p,station,start,end,identifier,path))
    assert len(jobs)+len(manifest['records'])==960
    def fetch(job):
        p,station,start,end,identifier,path=job
        client=QualityRoadClient(p,key,out/'transport',session=LimitedSession(throttle));frames=[];records=[];invalid=0
        cursor=start;chunk=360 if station=='33402' else 1440
        while cursor<=end:
            finish=min(cursor+pd.Timedelta(minutes=chunk-1),end)
            body,r=client.fetch(station,cursor,finish);minute=parse_observations(body,station,cursor,finish)
            invalid+=int(minute.attrs.get('invalid_timestamp_rows_excluded',0));frames.append(minute);records+=r;cursor=finish+pd.Timedelta(minutes=1)
        f=pd.concat(frames,ignore_index=True);assert not f.duplicated(['station','time']).any()
        return job,exact_ten_minute_grid(f),len(f),records,invalid
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures=[executor.submit(fetch,job) for job in jobs]
        try:
            for future in as_completed(futures):
                (p,station,start,end,identifier,path),frame,minute_rows,records,invalid=future.result()
                frame.to_parquet(path,index=False,compression='zstd')
                manifest['records'][identifier]=dict(station=station,start_kst=start.isoformat(),end_kst=end.isoformat(),
                    downloaded_at_utc=now(),sha256=sha(path),rows=len(frame),minute_rows=minute_rows,transport=records,
                    invalid_timestamp_rows_excluded=invalid,controller='globally_throttled_resume')
                atomic_write(mp,manifest)
                if len(manifest['records'])%20==0:print('COLLECT',len(manifest['records']),'/ 960',flush=True)
        except BaseException:
            for future in futures:future.cancel()
            raise
    assert len(manifest['records'])==960
    manifest.update(status='complete',completed_at_utc=now());atomic_write(mp,manifest);verify(out);old_freezes()
    print('COLLECTION COMPLETE',flush=True)


if __name__=='__main__':main()
