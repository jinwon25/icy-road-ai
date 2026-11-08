"""같은 기상 표현에 서로 다른 상태가 붙는 개발 자료 충돌을 진단한다."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.icing_precision_20261106 import features
from src.data_source import sha256_file as sha

def main():
    p=ROOT/'outputs/private/blind_icing_20261025_v2/training.parquet'
    out=ROOT/'outputs/private/icing_input_identifiability_20261106'
    assert not out.exists()
    f=pd.read_parquet(p).sort_values(['station','time']).reset_index(drop=True)
    assert len(set(f.station))==23 and not set(f.station)&{'12410','33411','23402','33402','33406','12213','23411'}
    valid=f.available&f.ice.isin([0,1]);source=f.loc[valid]
    results={}
    tables=[]
    for kind in ['snapshot','process']:
        x=features(f,kind).loc[valid]
        h=pd.util.hash_pandas_object(x,index=False).to_numpy()
        q=source[['station','time','ice']].copy();q['input_hash']=h
        table=q.groupby('input_hash').agg(rows=('ice','size'),ice=('ice','sum'),stations=('station','nunique')).reset_index()
        table['negative']=table.rows-table.ice
        table['mixed']=table.ice.gt(0)&table.negative.gt(0)
        table['minimum_row_errors_for_fixed_exact_input']=np.minimum(table.ice,table.negative)
        mixed=set(table.loc[table.mixed,'input_hash'])
        # 모든 혼합 그룹의 실제 float 입력을 대조해 해시 충돌 가능성을 제거한다.
        for key,idx in q.loc[q.input_hash.isin(mixed)].groupby('input_hash').groups.items():
            arr=x.loc[idx].to_numpy(float)
            if not np.all((arr==arr[0])|(np.isnan(arr)&np.isnan(arr[0]))):raise AssertionError('Hash collision')
        ambiguous=q.loc[q.input_hash.isin(mixed)]
        examples=ambiguous.groupby('input_hash').agg(stations=('station',lambda s:','.join(sorted(set(s)))),
            first_time=('time','min'),rows=('ice','size'),ice=('ice','sum')).reset_index().sort_values('ice',ascending=False)
        result=dict(features=len(x.columns),rows=len(q),observed_ice=int(q.ice.sum()),unique_input_vectors=len(table),
            mixed_input_vectors=int(table.mixed.sum()),positive_rows_in_mixed_vectors=int(table.loc[table.mixed,'ice'].sum()),
            mixed_vectors_across_stations=int((table.mixed&table.stations.gt(1)).sum()),
            minimum_empirical_row_errors=int(table.minimum_row_errors_for_fixed_exact_input.sum()),
            mixed_input_rows=len(ambiguous),exact_float_equality_verified=True)
        results[kind]=result;tables.append((kind,examples))
        print(kind,json.dumps(result,ensure_ascii=False),flush=True)
    out.mkdir()
    for kind,table in tables:table.to_csv(out/(kind+'_conflicting_weather_groups.csv'),index=False)
    summary=dict(status='exact_weather_input_conflicts_verified',at_utc=datetime.now(timezone.utc).isoformat(),
        input_sha256=sha(p),results=results,
        interpretation='고정된 기상 표현에서 관측된 동일 입력은 결정론적 모델이 구분할 수 없다. 관측 표본 내 충돌 진단이며 새 지역 오차의 하한·물리적 불가피성·정답 오류로 일반화하지 않는다. 도로환경·처리이력 등 누락 변수를 검토할 근거다.',
        protected_outcomes_used=False,external_four_outcomes_used=False,production_model_changed=False)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')

if __name__=='__main__':main()
