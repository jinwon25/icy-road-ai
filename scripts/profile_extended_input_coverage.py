"""정답을 읽지 않고 개발·제출 위치의 예측 입력 가용성을 비교한다."""
import json
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.thermal_runtime import thermal_predictors,EXTRA
from src.submission_runtime import FEATURES
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation


def main():
    private=ROOT/'outputs/private';out=private/'extended_input_coverage_20261024_v1'
    if out.exists():raise FileExistsError('Preserve input coverage audit')
    frozen=preservation();columns=list(dict.fromkeys(['station','time',*FEATURES,*EXTRA]))
    source=private/'canonical_thermal_data_20261024_v1/development.parquet'
    development=pd.read_parquet(source,columns=columns)
    x,valid,_=thermal_predictors(development,'thermal_history')
    development['winter']=development.time.dt.year.where(development.time.dt.month.ge(11),development.time.dt.year-1)
    records=[];sources={str(source.relative_to(ROOT)):sha(source)}
    def append(scope,key,winter,inputs):
        for feature in inputs:
            known=inputs[feature].notna()
            records.append(dict(scope=scope,id=str(key),winter=int(winter),feature=feature,
                rows=len(inputs),available=int(known.sum()),missing=int((~known).sum()),available_fraction=float(known.mean())))
    for (station,winter),part in development.groupby(['station','winter']):append('development',station,winter,x.loc[part.index])
    folder=private/'extended_delivery_inputs_20261024_v2'
    receipt=json.loads((folder/'receipt.json').read_text('utf-8'))
    for key,metadata in receipt['groups'].items():
        path=folder/'weather_groups'/(key+'.parquet');assert sha(path)==metadata['weather_sha256']
        f=pd.read_parquet(path,columns=columns);x,_,_=thermal_predictors(f,'thermal_history')
        append('delivery_weather_group',key,metadata['winter'],x)
    table=pd.DataFrame(records)
    pooled=table.groupby(['scope','feature'])[['rows','available','missing']].sum().reset_index()
    pooled['available_fraction']=pooled.available/pooled.rows
    assert preservation()==frozen
    out.mkdir();table.to_csv(out/'by_location_winter_feature.csv',index=False)
    pooled.to_csv(out/'pooled_feature_coverage.csv',index=False)
    summary=dict(status='input_coverage_verified',development_rows=len(development),development_temperature_eligible=int(valid.sum()),
        delivery_groups=len(receipt['groups']),protected_labels_read=False,development_labels_read=False,
        zero_imputation_performed=False,old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],
        interpretation='Missing precipitation, snow or radiation remains unknown, not zero. Missing optional predictors do not by themselves suppress a supported HGB temperature estimate.',
        source_signatures=sources|{str((folder/'receipt.json').relative_to(ROOT)):sha(folder/'receipt.json'),str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))},
        files={p.name:sha(p) for p in out.iterdir() if p.is_file()})
    (out/'receipt.json').write_text(json.dumps(summary,indent=2)+'\n','utf-8');print(summary,flush=True)

if __name__=='__main__':main()
