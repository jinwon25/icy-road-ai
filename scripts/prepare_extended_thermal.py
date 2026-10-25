"""허용 23곳·두 겨울에 기존 기상 열·수분 관측만 결합한다. 주변 노면 정답은 읽지 않는다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.method_blending import ALLOWED
from src.two_winter import validate
from src.temperature_transfer import THERMAL_FEATURES
from scripts.evaluate_method_blending import preservation

def main():
    private=ROOT/'outputs/private';out=private/'extended_thermal_data_20261024_v1'
    if out.exists():raise FileExistsError('Preserve thermal data')
    frozen=preservation();base=private/'two_winter_development_20261024_v1/development.parquet'
    data=validate(pd.read_parquet(base));columns=[c for c in THERMAL_FEATURES if c not in data]
    sources={str(base.relative_to(ROOT)):sha(base)}
    def load(path):
        ids=pd.read_parquet(path,columns=['station','time'])
        assert set(ids.station)<=ALLOWED and not ids.duplicated(['station','time']).any()
        sources[str(path.relative_to(ROOT))]=sha(path)
        return pd.read_parquet(path,columns=['station','time',*columns])
    parts=[load(private/'weather_distance_20261010_v1/development_inputs.parquet')]
    release=private/'releases/20261007/outputs/private'
    comp=load(release/'physical_features/features.parquet');parts.append(comp.loc[comp.time.ge('2025-11-01')])
    groups=data[['station','group']].drop_duplicates()
    for station in sorted(groups.loc[~groups.group.eq('competition'),'station']):
        parts.append(load(release/'external_reserved_predictions_v1'/('inputs_'+station+'.parquet')))
    joined=data.merge(pd.concat(parts,ignore_index=True),on=['station','time'],how='left',validate='one_to_one',indicator=True)
    assert joined._merge.eq('both').all();joined=joined.drop(columns='_merge')
    assert len(joined)==len(data) and not np.isinf(joined[THERMAL_FEATURES].to_numpy(float)).any()
    out.mkdir();joined.to_parquet(out/'development.parquet',index=False,compression='zstd')
    inventory=joined.groupby(['station','winter'])[columns].count();inventory.to_csv(out/'available_inputs.csv')
    assert preservation()==frozen
    (out/'receipt.json').write_text(json.dumps(dict(status='thermal_inputs_prepared',rows=len(joined),new_columns=columns,sources=sources,
        data_sha256=sha(out/'development.parquet'),protected_labels_read=False,neighbor_targets_read=False),ensure_ascii=False,indent=2)+'\n','utf-8')
    print('thermal data',len(joined),columns,flush=True)

if __name__=='__main__':main()
