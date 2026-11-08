"""허용23지점의 두 겨울 상태 정답을 키로 결합한다. 보호 정답 파일은 열지 않는다."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.icing_state_targets_20261106 import state_targets,STATE_GROUPS,NAMES
from src.data_source import sha256_file as sha
P=ROOT/'outputs/private';out=P/'icing_state_targets_20261106'
assert not out.exists()
source=P/'blind_icing_20261025_v2/training.parquet'
f=pd.read_parquet(source,columns=['station','time','ice'])
allowed=set(f.station)
assert len(allowed)==23 and not allowed&{'12410','33411','23402','33402','33406','12213','23411'}
paths=[P/'ice_group_balanced_20261009_v1/development_index.parquet',
       P/'releases/20261007/outputs/private/ice_features/features.parquet',
       P/'releases/20261007/outputs/private/external_reserved_assessment_v1/assessment.parquet']
parts=[]
for i,path in enumerate(paths):
    ids=pd.read_parquet(path,columns=['station'])
    assert set(ids.station)<=allowed
    q=pd.read_parquet(path,columns=['station','time','state_raw'])
    if i==1:q=q.loc[q.time.ge('2025-11-01')]
    parts.append(q)
labels=pd.concat(parts,ignore_index=True)
assert not labels.duplicated(['station','time']).any()
q=f.merge(labels,on=['station','time'],how='left',validate='one_to_one')
q['state_target']=state_targets(q.state_raw,q.ice)
assert len(q)==len(f)
out.mkdir()
q.to_parquet(out/'targets.parquet',index=False,compression='zstd')
receipt=dict(status='allowed_multistate_targets_prepared',at_utc=datetime.now(timezone.utc).isoformat(),
             rows=len(q),stations=sorted(allowed),mapping=STATE_GROUPS,names=NAMES,
             counts={str(k):int(v) for k,v in q.state_target.value_counts(dropna=False).items()},
             sources={str(p.relative_to(ROOT)):sha(p) for p in [source,*paths]},
             targets_sha256=sha(out/'targets.parquet'),protected_outcomes_used=False,external_four_outcomes_used=False)
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(receipt,ensure_ascii=False),flush=True)
