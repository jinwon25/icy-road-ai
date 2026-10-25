"""봉인된 감사 코드의 빈 Parquet 시각 dtype 문제만 보완한다. 관측·예측·지표는 바꾸지 않는다."""
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import audit_blind_icing as original
from scripts.blind_icing_validation import DEFAULT,read,write,now
from src.data_source import sha256_file as sha


def typed_empty_time(frame):
    if frame.empty and 'time' in frame:
        result=frame.copy();result['time']=pd.to_datetime(result.time);return result
    return frame


def main():
    out=DEFAULT
    if (out/'result_audit.json').exists():raise FileExistsError('Preserve completed audit')
    summary_sha=sha(out/'summary.json');reader=pd.read_parquet;changed=[]
    def adapter(path,*args,**kwargs):
        frame=reader(path,*args,**kwargs)
        if frame.empty and 'time' in frame:changed.append(str(path))
        return typed_empty_time(frame)
    write(out/'result_audit_empty_repair.json',dict(at_utc=now(),original_error='AttributeError at g.time.dt on an empty observation parquet',
        repair='Only cast time dtype in empty in-memory frames. No rows, persisted files, predictions, metric definitions or summaries changed.',
        original_audit_code_sha256=sha(ROOT/'scripts/audit_blind_icing.py'),adapter_sha256=sha(Path(__file__)),summary_sha256=summary_sha))
    try:
        pd.read_parquet=adapter;original.audit_result(out)
    finally:pd.read_parquet=reader
    assert sha(out/'summary.json')==summary_sha
    write(out/'result_audit_adapter_receipt.json',dict(status='passed',empty_frames_typed=len(changed),empty_paths=changed,
        persisted_observations_modified=False,summary_sha256=summary_sha,original_result_audit_sha256=sha(out/'result_audit.json'),adapter_sha256=sha(Path(__file__))))


if __name__=='__main__':main()
