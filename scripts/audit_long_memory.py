"""원천 행의 정수 누적합과 정규 격자의 별도 rolling을 전체 허용 자료에서 대조한다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.followup_temperature import LONG_MEMORY_COLUMNS,long_memory
from src.two_winter import validate


def main():
    source=ROOT/'outputs/private/solar_memory_data_20261024_v1/development.parquet'
    plan=json.loads((ROOT/'outputs/private/followup_temperature_20261024_v1/plan.json').read_text('utf-8'))
    assert sha(source)==plan['signatures']['data']
    out=ROOT/'outputs/private/followup_long_memory_audit_20261024_v1'
    if out.exists():raise FileExistsError('Preserve independent feature audit')
    f=validate(pd.read_parquet(source,columns=['station','time','winter',*LONG_MEMORY_COLUMNS])).sort_values(['station','time']).reset_index(drop=True)
    actual=long_memory(f);reference=pd.DataFrame(np.nan,index=f.index,columns=actual.columns)
    for (_,winter),part in f.groupby(['station','winter']):
        grid=pd.date_range(f'{winter}-11-01',f'{winter+1}-03-01',inclusive='left',freq='10min')
        complete=part.set_index('time').reindex(grid)
        for c in LONG_MEMORY_COLUMNS:
            values=(complete[c]*1_000_000).round()
            for minutes in [1440,2880]:
                n=minutes//10;valid=values.notna().astype(int).rolling(n,closed='left',min_periods=1).sum()
                total=values.rolling(n,closed='left',min_periods=int(np.ceil(.8*n))).sum()
                expected=(total/(valid*1_000_000)).round(6).reindex(part.time)
                reference.loc[part.index,f'{c}_prior_mean_{minutes}m']=expected.to_numpy()
    pd.testing.assert_frame_equal(actual,reference,check_exact=True)
    out.mkdir(parents=True)
    receipt=dict(status='all_long_memory_values_exactly_verified',rows=len(f),features=len(actual.columns),
        values=actual.size,missing_values=int(actual.isna().sum().sum()),
        reference_method='separate complete 10-minute calendar + rolling fixed-point integer sum/count',
        input_sha256=sha(source),feature_module_sha256=sha(ROOT/'src/followup_temperature.py'),
        audit_sha256=sha(Path(__file__)),outcome_columns_read=False,protected_rows_read=False)
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('Long memory audit passed',actual.size,flush=True)


if __name__=='__main__':main()
