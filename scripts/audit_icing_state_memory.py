"""순차 루프 대신 구간별 누적합·전방 채움으로 15개 상태 정책의 전체 출력을 검산한다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.two_winter import validate
from scripts.evaluate_method_blending import preservation


def vectorized_reference(frame,prediction,temperature,spec):
    f=frame[['station','time']].copy();f['position']=np.arange(len(f))
    f['raw']=np.asarray(prediction);f['temperature']=np.asarray(temperature)
    result=np.full(len(f),np.nan)
    for _,part in f.groupby('station'):
        q=part.sort_values('time').reset_index(drop=True)
        missing=q.raw.isna()|q.temperature.isna()
        gap=~q.time.diff().eq(pd.Timedelta(minutes=10))
        positive=q.raw.eq(1)&~missing
        runs=positive.groupby((gap|~positive).cumsum()).cumsum()
        trigger=positive&runs.ge(spec['confirmation'])
        barriers=gap|missing|(~trigger&q.temperature.gt(spec['release_c']))
        last=q.time.where(trigger).groupby(barriers.cumsum()).ffill()
        held=q.time.sub(last).le(pd.Timedelta(minutes=spec['hold_minutes']))&q.temperature.le(spec['release_c'])
        out=(trigger|held).astype(float).where(~missing)
        result[q.position.to_numpy()]=out.to_numpy()
    return result


def main():
    source=ROOT/'outputs/private/icing_state_memory_20261024_v1'
    out=ROOT/'outputs/private/icing_state_memory_audit_20261024_v1'
    if out.exists():raise FileExistsError('Preserve independent state audit')
    frozen=preservation();plan=json.loads((source/'plan.json').read_text('utf-8'))
    for name,expected in plan['signatures'].items():assert sha(ROOT/name)==expected,name
    summary=json.loads((source/'summary.json').read_text('utf-8'))
    for name,expected in summary['files'].items():assert sha(source/name)==expected,name
    frame=validate(pd.read_parquet(ROOT/plan['settings']['baseline'])).sort_values(['station','time']).reset_index(drop=True)
    output=pd.read_parquet(source/'predictions.parquet')
    pd.testing.assert_frame_equal(frame[['station','time','ice']],output[['station','time','ice']],check_exact=True)
    checks=[]
    for name,spec in plan['policies'].items():
        expected=vectorized_reference(frame,frame.physical_both,frame.temperature_both,spec)
        np.testing.assert_array_equal(expected,output[name])
        checks.append(dict(policy=name,rows=len(frame),exact_match=True))
    assert preservation()==frozen
    out.mkdir(parents=True)
    receipt=dict(status='all_state_policy_predictions_independently_verified',policies=len(checks),
        values=sum(r['rows'] for r in checks),checks=checks,summary_sha256=sha(source/'summary.json'),
        audit_sha256=sha(Path(__file__)),protected_labels_read=False,frozen_counts=list(frozen))
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('State policy audit passed',len(checks),receipt['values'],flush=True)


if __name__=='__main__':main()
