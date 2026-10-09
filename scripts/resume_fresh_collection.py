"""고정 예측은 보존하고 공유 요청 간격을 지키는 제한 동시 전송으로 수집을 이어간다."""
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import argparse,json,sys,threading,time,shutil
import requests,pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.fresh_station_validation import DEFAULT_OUT,PRIVATE,read,write,verify_seal,old_freezes
from src.data_source import sha256_file as sha
from src.kma_rwis_download import daily_requests,load_auth_key,parse_observations,exact_ten_minute_grid
from src.kma_rwis_transport import ValidatedRoadClient


class SharedRequestInterval:
    def __init__(self,interval):
        if interval<1.2:raise ValueError('Keep the approved minimum request interval')
        self.interval=interval;self.last=time.perf_counter();self.lock=threading.Lock();self.starts=[]
    def before_request(self):
        with self.lock:
            while True:
                now=time.perf_counter();remaining=self.interval-(now-self.last)
                if remaining<=0:break
                time.sleep(max(remaining,.001))
            self.last=now
            self.starts.append(self.last)


class ThrottledSession(requests.Session):
    def __init__(self,limiter):super().__init__();self.limiter=limiter
    def get(self,*args,**kwargs):
        self.limiter.before_request();return super().get(*args,**kwargs)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',type=Path,default=DEFAULT_OUT);parser.add_argument('--credentials-file',type=Path);parser.add_argument('--workers',type=int,default=3,choices=[1,2,3]);args=parser.parse_args();out=args.experiment.resolve()
    if not out.is_relative_to(PRIVATE.resolve()):parser.error('Private experiment required')
    verify_seal(out);assert read(out/'prediction_audit.json')['status']=='passed'
    plan=read(out/'plan.json');manifest_path=out/'download_manifest.json';manifest=read(manifest_path)
    if manifest.get('status')=='complete':raise ValueError('Collection already complete')
    lock_path=out/'collection.lock'
    # 공유 제한기는 이 프로세스 내부에서 동작한다. 이전 순차 수집기는 종료한 뒤 실행한다.
    with lock_path.open('x',encoding='utf-8') as f:f.write(str(__import__('os').getpid()))
    run=out/f'collection_run_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}'
    run.mkdir();shutil.copy2(__file__,run/'collector_source.py')
    receipt=dict(started_at_utc=datetime.now(timezone.utc).isoformat(),workers=args.workers,global_minimum_request_interval_seconds=plan['minimum_request_interval_seconds'],
                 source_sha256=sha(__file__),plan_sha256=sha(out/'plan.json'),prediction_seal_sha256=sha(out/'prediction_seal.json'),credential_values_recorded=False,protocol_changed=False,timer='perf_counter with minimum-interval recheck')
    write(run/'receipt.json',receipt)
    key=load_auth_key(args.credentials_file);limiter=SharedRequestInterval(plan['minimum_request_interval_seconds']);local=threading.local()
    jobs=list(daily_requests(plan,plan['development_start_kst'],plan['development_end_kst'],window_minutes=plan['window_minutes']))
    pending=[]
    for station,start,end in jobs:
        identifier=f'{station}_{start:%Y%m%d%H%M}';path=out/'observations'/(identifier+'.parquet')
        if identifier in manifest['records']:
            assert path.exists() and sha(path)==manifest['records'][identifier]['sha256']
        else:pending.append((station,start,end))
    def fetch(job):
        station,start,end=job
        if not hasattr(local,'client'):local.client=ValidatedRoadClient(plan,key,out/'transport',session=ThrottledSession(limiter))
        body,transport=local.client.fetch(station,start,end);minute=parse_observations(body,station,start,end);frame=exact_ten_minute_grid(minute)
        identifier=f'{station}_{start:%Y%m%d%H%M}';path=out/'observations'/(identifier+'.parquet')
        if path.exists():
            # 강제 종료 사이에 미기록 파일이 남았다면 원본을 보존하고 검증 응답으로 복구한다.
            orphan=run/(identifier+'.unrecorded.parquet');path.rename(orphan)
        frame.to_parquet(path,index=False,compression='zstd')
        r=dict(station=station,start_kst=start.isoformat(),end_kst=end.isoformat(),downloaded_at_utc=datetime.now(timezone.utc).isoformat(),sha256=sha(path),rows=len(frame),minute_rows=len(minute),transport=transport,invalid_timestamp_rows_excluded=int(minute.attrs.get('invalid_timestamp_rows_excluded',0)))
        return identifier,r
    try:
        iterator=iter(pending)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(fetch,job) for job in [next(iterator,None) for _ in range(args.workers)] if job is not None}
            while futures:
                done,futures=wait(futures,return_when=FIRST_COMPLETED)
                for f in done:
                    identifier,r=f.result();manifest['records'][identifier]=r;write(manifest_path,manifest)
                    if len(manifest['records'])%32==0:print(f"Fresh validation collection {len(manifest['records'])}/{len(jobs)}",flush=True)
                    job=next(iterator,None)
                    if job is not None:futures.add(pool.submit(fetch,job))
        assert len(manifest['records'])==len(jobs);manifest['completed_at_utc']=datetime.now(timezone.utc).isoformat();manifest['status']='complete';write(manifest_path,manifest)
        verify_seal(out);old_freezes()
        write(run/'request_start_intervals.json',[b-a for a,b in zip(limiter.starts,limiter.starts[1:])])
        receipt.update(completed_at_utc=manifest['completed_at_utc'],status='complete',records=len(manifest['records']),request_start_intervals_sha256=sha(run/'request_start_intervals.json'));write(run/'receipt.json',receipt)
        print('Fresh validation collection completed:',len(jobs),flush=True)
    finally:
        # 이 작업의 잠금만 해제한다. 관측·전송 원본은 지우지 않는다.
        lock_path.unlink(missing_ok=True)


if __name__=='__main__':main()
