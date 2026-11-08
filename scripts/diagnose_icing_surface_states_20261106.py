"""기존 개발 지점의 오경보를 유효 노면상태 코드로만 분해한다."""
from pathlib import Path
import json
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'outputs/private'
a=pd.read_parquet(P/'ice_group_balanced_20261009_v1/development_index.parquet',columns=['station','time','state_raw'])
b=pd.read_parquet(P/'releases/20261007/outputs/private/external_reserved_assessment_v1/assessment.parquet',columns=['station','time','state_raw'])
for f in [a,b]:
    assert not set(f.station)&{'12410','33411','23402','33402','33406','12213','23411'}
labels=pd.concat([a,b],ignore_index=True)
assert not labels.duplicated(['station','time']).any()
q=pd.read_parquet(P/'two_winter_models_20261024_v1/runtime_predictions.parquet',columns=['station','time','ice','physical_both'])
q=q.merge(labels,on=['station','time'],validate='one_to_one')
q['state']=pd.to_numeric(q.state_raw,errors='coerce').astype('Int64')
q['tp']=q.ice.eq(1)&q.physical_both.eq(1)
q['fp']=q.ice.eq(0)&q.physical_both.eq(1)
q['fn']=q.ice.eq(1)&q.physical_both.eq(0)
table=q.groupby('state',dropna=False).agg(rows=('time','size'),tp=('tp','sum'),fp=('fp','sum'),fn=('fn','sum')).reset_index()
out=P/'icing_precision_diagnosis_20261106'
table.to_csv(out/'false_alarm_surface_states.csv',index=False)
result=dict(status='allowed_development_surface_state_diagnosis',rows=len(q),states=table.fillna(-1).to_dict('records'),
            protected_outcomes_used=False,external_four_outcomes_used=False,no_model_input_or_label_changed=True)
(out/'state_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
print(table.to_string(index=False),flush=True)
