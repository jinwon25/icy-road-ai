"""허용 지점 기상·전국 DSM/태양 위치를 키로 결합한다. 노면 온도 입력 없음."""
from pathlib import Path
import sys,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.icing_local_context_20261106 import AWS,TERRAIN,features
from src.data_source import sha256_file as sha
P=ROOT/'outputs/private';out=P/'icing_local_context_inputs_20261106'
assert not out.exists()
paths=[P/'blind_icing_20261025_v2/training.parquet',
       P/'solar_memory_data_20261024_v1/development.parquet',
       P/'terrain_thermal_data_20261024_v1/development.parquet']
f=pd.read_parquet(paths[0]).sort_values(['station','time']).reset_index(drop=True)
blocked={'12410','33411','23402','33402','33406','12213','23411'}
for path,columns in [(paths[1],['station','time',*AWS,'aws_age_minutes']),(paths[2],['station','time',*TERRAIN])]:
    ids=pd.read_parquet(path,columns=['station'])
    assert not set(ids.station)&blocked and set(ids.station)==set(f.station)
    extra=pd.read_parquet(path,columns=columns)
    f=f.merge(extra,on=['station','time'],validate='one_to_one')
assert len(set(f.station))==23
x={kind:features(f,kind) for kind in ['process','local','terrain']}
out.mkdir();f.to_parquet(out/'training.parquet',index=False,compression='zstd')
receipt=dict(status='local_context_inputs_prepared',rows=len(f),stations=sorted(f.station.unique()),
             feature_names={k:list(v) for k,v in x.items()},feature_counts={k:len(v.columns) for k,v in x.items()},
             sources={p.relative_to(ROOT).as_posix():sha(p) for p in paths},sha256=sha(out/'training.parquet'),
             forbidden_road_observation_inputs=['road_temp','state_raw','neighbour_road_state'],
             elevation_units='Copernicus DSM actual metres; competition normalized DEM unused',
             static_feature_caveat='DSM/일사 입력은 지역 제외 평가로 검증하며 설치 지점의 교량/포장/제설을 재현한다고 주장하지 않음',
             protected_outcomes_used=False,external_four_outcomes_used=False)
(out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
print(receipt['feature_counts'],flush=True)
