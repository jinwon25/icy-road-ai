"""같은 기상 입력에서 다른 정답이 나타나는 빈도를 계산한다. 센서 오류로 단정하지 않는다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.two_winter import validate
from src.submission_runtime import FEATURES
from src.thermal_extended import feature_table

def main():
    private=ROOT/'outputs/private';out=private/'weather_identifiability_20261024_v1'
    if out.exists():raise FileExistsError('Preserve identifiability audit')
    source=private/'extended_thermal_data_20261024_v1/development.parquet'
    f=validate(pd.read_parquet(source));out.mkdir();results={}
    for kind in ['weather','history','thermal']:
        x=feature_table(f,kind);x['_ice']=f.ice.to_numpy();valid=x.loc[f.ice.notna()]
        group=valid.groupby(list(x.columns[:-1]),dropna=False)._ice.agg(['count','sum'])
        mixed=group['sum'].gt(0)&group['sum'].lt(group['count'])
        results[kind]=dict(rows=len(valid),positive_rows=int(valid._ice.sum()),unique_exact_inputs=len(group),mixed_groups=int(mixed.sum()),
            mixed_rows=int(group.loc[mixed,'count'].sum()),positive_rows_in_mixed_groups=int(group.loc[mixed,'sum'].sum()),
            deterministic_row_error_lower_bound=int(np.minimum(group['sum'],group['count']-group['sum']).sum()),features=len(x.columns)-1)
        # 다른 지점·같은 시각의 충돌만 따로 세어 날짜 반복과 구별한다.
        valid=valid.copy();valid['_time']=f.loc[valid.index,'time'].to_numpy()
        groups=valid.groupby([*x.columns[:-1],'_time'],dropna=False)._ice.agg(['count','sum'])
        results[kind]['same_time_mixed_groups']=int(((groups['sum']>0)&(groups['sum']<groups['count'])).sum())
        print(kind,results[kind],flush=True)
    weather=f.loc[f.ice.notna()].copy();nunique=weather.groupby(list(FEATURES),dropna=False).ice.transform('nunique')
    weather['mixed']=nunique.gt(1);weather['positive_mixed']=weather.ice.eq(1)&weather.mixed
    weather.groupby(['station','winter']).agg(rows=('ice','size'),ice=('ice','sum'),mixed_rows=('mixed','sum'),positive_mixed=('positive_mixed','sum')).to_csv(out/'station_winter_conflicts.csv')
    (out/'summary.json').write_text(json.dumps(dict(status='weather_identifiability_audited',results=results,source_sha256=sha(source),
        interpretation='같은 입력으로 같은 판정을 내는 결정적 모형의 행 단위 오류 하한. 공식 일별 F1의 상한이 아니며 센서 고장·오라벨을 입증하지 않음',
        protected_labels_read=False),ensure_ascii=False,indent=2)+'\n','utf-8')

if __name__=='__main__':main()
