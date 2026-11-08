"""가까운 AWS 관측이 ASOS만의 동일 입력 충돌을 줄이는지 확인한다."""
from pathlib import Path
import sys,json
import pandas as pd,numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.icing_precision_20261106 import features
P=ROOT/'outputs/private';out=P/'icing_local_weather_feasibility_20261106'
assert not out.exists()
a=pd.read_parquet(P/'blind_icing_20261025_v2/training.parquet').sort_values(['station','time']).reset_index(drop=True)
local=pd.read_parquet(P/'solar_memory_data_20261024_v1/development.parquet',columns=['station','time','aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint','aws_age_minutes'])
assert set(a.station)==set(local.station)
a=a.merge(local,on=['station','time'],validate='one_to_one')
cols=['aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint']
valid_aws=a.aws_age_minutes.between(0,60,inclusive='right')
for c in cols:a[c]=a[c].where(valid_aws)
x=pd.concat([features(a,'process'),a[cols+['aws_age_minutes']]],axis=1)
keep=a.available&a.ice.isin([0,1]);q=a.loc[keep,['station','time','ice']].copy()
q['hash']=pd.util.hash_pandas_object(x.loc[keep],index=False).to_numpy()
table=q.groupby('hash').ice.agg(['size','sum'])
mixed=table['sum'].gt(0)&table['sum'].lt(table['size'])
result=dict(rows=len(q),features=len(x.columns),observed_ice=int(q.ice.sum()),unique_vectors=len(table),
            positive_rows_with_conflicting_exact_inputs=int(table.loc[mixed,'sum'].sum()),
            minimum_empirical_row_errors=int(np.minimum(table['sum'],table['size']-table['sum']).sum()),
            note='관측 표본 입력 식별 진단. 독립 성능 향상으로 주장하지 않음. 해시를 실제 배열과 추가 검산하는 것은 최종 진단에서 수행.')
out.mkdir();(out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(result,ensure_ascii=False),flush=True)
