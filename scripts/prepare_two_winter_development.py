"""비보호 둘째 겨울을 새 개발본에 결합한다. 보호 정답과 과거 예측 열을 읽지 않는다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.method_blending import ALLOWED
from src.submission_runtime import FEATURES
from src.validation import PROTECTED_STATIONS
from scripts.baseline_ice_logistic import add_time_features
from scripts.evaluate_method_blending import preservation


def main():
    private=ROOT/'outputs/private';release=private/'releases/20261007/outputs/private'
    out=private/'two_winter_development_20261024_v1'
    if out.exists():raise FileExistsError('Preserve prepared data')
    plan=json.loads((ROOT/'config/two_winter_development_20261024.json').read_text('utf-8'))
    assert set(plan['allowed_stations'])==ALLOWED and not ALLOWED&PROTECTED_STATIONS
    frozen=preservation();signatures={}
    def checked(path,columns=None):
        identities=pd.read_parquet(path,columns=['station','time'])
        if not set(identities.station.astype(str))<=ALLOWED:raise ValueError('Non-development station in source')
        if identities.duplicated(['station','time']).any():raise ValueError('Duplicate source keys')
        signatures[str(path.relative_to(ROOT))]=sha(path)
        return pd.read_parquet(path,columns=columns)
    first=checked(private/'submission_candidate_20261019_v1/data/research_weather_inputs.parquet')
    labels=checked(private/'ice_group_balanced_20261009_v1/development_index.parquet',['station','time','ice','group'])
    first=first.merge(labels,on=['station','time'],validate='one_to_one')
    comp=checked(release/'ice_features/features.parquet')
    comp=comp.loc[comp.time.ge('2025-11-01')].copy()
    temps=checked(release/'point_sources/rwis.parquet',['station','time','road_temp'])
    comp=comp.merge(temps,on=['station','time'],validate='one_to_one')
    comp=add_time_features(comp);comp['group']='competition'
    group_map=labels[['station','group']].drop_duplicates().set_index('station').group.to_dict()
    # 과거 assessment의 예측 열은 읽지 않고, 적격 지점·시각 확인 후 관측 세 열만 사용한다.
    observed=checked(release/'external_reserved_assessment_v1/assessment.parquet',['station','time','ice','road_temp'])
    externals=[]
    for station in sorted(observed.station.unique()):
        inputs=checked(release/'external_reserved_predictions_v1'/('inputs_'+station+'.parquet'),['station','time',*FEATURES])
        part=inputs.merge(observed.loc[observed.station.eq(station)],on=['station','time'],validate='one_to_one')
        part['group']=group_map[station];externals.append(part)
    columns=['station','time','group','ice','road_temp',*FEATURES]
    frame=pd.concat([first[columns],comp[columns],*[f[columns] for f in externals]],ignore_index=True)
    frame['winter']=np.where(frame.time.dt.year.le(2025)&frame.time.lt('2025-03-01'),2024,2025)
    assert not frame.duplicated(['station','time']).any() and set(frame.station)==ALLOWED
    valid_time=(frame.time.ge('2024-11-01')&frame.time.lt('2025-03-01'))|(frame.time.ge('2025-11-01')&frame.time.lt('2026-03-01'))
    assert valid_time.all() and (frame.time.dt.minute%10==0).all()
    out.mkdir();frame.to_parquet(out/'development.parquet',index=False,compression='zstd')
    counts=frame.groupby(['winter','group','station']).agg(rows=('time','size'),valid_ice=('ice','count'),ice_slots=('ice','sum')).reset_index()
    counts.to_csv(out/'training_inventory.csv',index=False,encoding='utf-8-sig')
    assert preservation()==frozen
    receipt=dict(status='two_winter_development_prepared',rows=len(frame),stations=sorted(frame.station.unique()),
        plan_sha256=sha(ROOT/'config/two_winter_development_20261024.json'),sources=signatures,
        data_sha256=sha(out/'development.parquet'),old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],
        protected_labels_read=False,previous_prediction_columns_read=False,new_independent_assessment=False)
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(counts.to_string(index=False));print('prepared',len(frame),flush=True)


if __name__=='__main__':main()
