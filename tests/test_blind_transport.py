import json
from scripts import resume_blind_icing_transport as transport


def test_throttle_rechecks_elapsed_time_after_short_sleep(tmp_path,monkeypatch):
    clock={'time':10.,'sleeps':0}
    monkeypatch.setattr(transport.time,'monotonic',lambda:clock['time'])
    def early_sleep(duration):
        clock['sleeps']+=1
        clock['time']+=max(.001,duration-.03)
    monkeypatch.setattr(transport.time,'sleep',early_sleep)
    log=tmp_path/'requests.jsonl';gate=transport.GlobalThrottle(1.2,log)
    params=dict(var='33402',tm1='202411010000',tm2='202411010559',authKey='do-not-log')
    for _ in range(3):gate.wait(params)
    rows=[json.loads(x) for x in log.read_text('utf-8').splitlines()]
    assert all(b['monotonic']-a['monotonic']>=1.2 for a,b in zip(rows,rows[1:]))
    assert clock['sleeps']>2 and 'do-not-log' not in log.read_text('utf-8')


def test_atomic_manifest_retry_preserves_complete_record(tmp_path,monkeypatch):
    from pathlib import Path
    original=Path.replace;calls=[]
    def sometimes_locked(self,target):
        calls.append(self)
        if len(calls)==1:raise PermissionError('simulated Windows sharing violation')
        return original(self,target)
    monkeypatch.setattr(Path,'replace',sometimes_locked)
    monkeypatch.setattr(transport.time,'sleep',lambda seconds:None)
    target=tmp_path/'manifest.json';target.write_text('{"old":1}','utf-8')
    transport.atomic_write(target,{'old':1,'new':2})
    assert json.loads(target.read_text('utf-8'))=={'old':1,'new':2} and len(calls)==2
