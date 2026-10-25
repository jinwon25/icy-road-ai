"""평가 지역을 보정 단계에서도 제외한 상수 오차 보정: 6개 이중 제외 적합."""
from itertools import combinations
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.two_winter import validate
from src.solar_memory_search import feature_table
from src.extended_search import estimator,temperature_gate
from src.extended_comparison import block_sensitivity
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation


def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')


def offsets(frame,maximum):
    valid=frame.road_temp.notna()&frame.prediction.notna()
    f=frame.loc[valid,['station','road_temp','prediction']].copy();f['residual']=f.road_temp-f.prediction
    if f.empty:raise ValueError('Nonempty calibration residuals required')
    return dict(pooled_median=float(np.clip(f.residual.median(),-maximum,maximum)),
                station_median=float(np.clip(f.groupby('station').residual.median().median(),-maximum,maximum)))


def main():
    config=ROOT/'config/followup_offset_20261024.json';plan=read(config)
    out=ROOT/'outputs/private/followup_offset_20261024_v1';source=ROOT/plan['data'];reference=ROOT/plan['reference']
    reference_report=read(reference/'report.json');original_plan=read(reference.parent/'plan.json')
    assert sha(source)==original_plan['signatures']['data']
    signatures={str(p.relative_to(ROOT)):sha(p) for p in [config,source,Path(__file__),ROOT/'src/solar_memory_search.py',
        ROOT/'src/combined_thermal_history.py',ROOT/'src/thermal_extended.py',ROOT/'src/extended_search.py',reference/'report.json',reference/'predictions.parquet']}
    if out.exists():assert read(out/'plan.json')['signatures']==signatures
    else:out.mkdir(parents=True);write(out/'plan.json',dict(settings=plan,signatures=signatures,started_at_utc=datetime.now(timezone.utc).isoformat()))
    frozen=preservation()
    data=validate(pd.read_parquet(source)).sort_values(['station','time']).reset_index(drop=True)
    base=validate(pd.read_parquet(reference/'predictions.parquet'))
    pd.testing.assert_frame_equal(base[['station','time']],data.loc[data.group.ne('competition'),['station','time']].reset_index(drop=True))
    groups=sorted(base.group.unique());x=feature_table(data,plan['feature_kind']);stored={};fit_receipts=[]
    spec=dict(family='hgb',loss=plan['loss'],iterations=plan['iterations'],leaves=31)
    folder=out/'models';folder.mkdir(exist_ok=True)
    for pair in combinations(groups,2):
        stem='__'.join(pair);record=folder/(stem+'.json');modelpath=folder/(stem+'.joblib');predpath=folder/(stem+'.parquet')
        train=data.loc[~data.group.isin(pair)&data.road_temp.notna()&data.asos_air_temp.notna()]
        query=data.loc[data.group.isin(pair)]
        assert not set(train.station)&set(query.station)
        if record.exists():
            receipt=read(record);assert sha(modelpath)==receipt['model_sha256'] and sha(predpath)==receipt['prediction_sha256']
            f=pd.read_parquet(predpath)
        else:
            model=estimator(spec,plan['seed'],plan['threads']);started=time.perf_counter()
            with deny_network() as attempts,threadpool_limits(limits=plan['threads']):
                model.fit(x.loc[train.index],train.road_temp.to_numpy())
                pred=model.predict(x.loc[query.index])
            assert not attempts and model.n_iter_==1200
            f=query[['station','time','group','winter','ice','road_temp','asos_air_temp']].copy().reset_index(drop=True)
            f['prediction']=np.where(query.asos_air_temp.notna(),pred,np.nan)
            f.to_parquet(predpath,index=False,compression='zstd');joblib.dump(model,modelpath,compress=3)
            receipt=dict(excluded_groups=list(pair),training_stations=sorted(train.station.unique()),training_rows=len(train),
                features=list(x),parameters=model.get_params(),model_sha256=sha(modelpath),prediction_sha256=sha(predpath),
                seconds=time.perf_counter()-started,protected_labels_read=False)
            write(record,receipt);print('NESTED OFFSET',stem,round(receipt['seconds'],1),flush=True)
        # 실제 저장 파일을 재로딩해 적합 상태·행키·예측을 확인한다.
        model=joblib.load(modelpath)
        pd.testing.assert_frame_equal(f[['station','time']],query[['station','time']].reset_index(drop=True),check_exact=True)
        assert receipt['training_stations']==sorted(train.station.unique()) and receipt['training_rows']==len(train)
        with deny_network() as attempts,threadpool_limits(limits=2):actual=model.predict(x.loc[query.index])
        assert not attempts
        np.testing.assert_allclose(np.where(query.asos_air_temp.notna(),actual,np.nan),f.prediction,rtol=0,atol=1e-12,equal_nan=True)
        stored[pair]=f;fit_receipts.append(receipt)
    output=base.copy();decisions={}
    for policy in plan['policies']:output[policy]=np.nan
    for outer in groups:
        calibration=pd.concat([stored[tuple(sorted([outer,h]))].loc[lambda f:f.group.eq(h)] for h in groups if h!=outer],ignore_index=True)
        assert outer not in set(calibration.group)
        selected=offsets(calibration,plan['maximum_absolute_offset_c'])
        decisions[outer]=dict(offsets=selected,calibration_groups=sorted(calibration.group.unique()),
            calibration_stations=sorted(calibration.station.unique()),calibration_valid_rows=int((calibration.road_temp.notna()&calibration.prediction.notna()).sum()),outer_outcomes_used=False)
        mask=output.group.eq(outer)
        for policy,offset in selected.items():output.loc[mask,policy]=output.loc[mask,'prediction']+offset
    reports={};gate_plan=read(ROOT/'config/followup_temperature_20261024.json')['temperature_gate']
    for policy in plan['policies']:
        reports[policy]=temperature_gate(output,output[policy],base.prediction,gate_plan)
        reports[policy]['date_sensitivity']=block_sensitivity(output,output[policy],base.prediction)
        print('RESULT',policy,reports[policy]['regression']['pooled']['mae'],reports[policy]['gates'],flush=True)
    output.to_parquet(out/'predictions.parquet',index=False,compression='zstd')
    write(out/'decisions.json',decisions)
    final_offsets=offsets(base,plan['maximum_absolute_offset_c'])
    assert preservation()==frozen
    write(out/'summary.json',dict(status='nested_offset_comparison_complete',reports=reports,final_refit_offsets=final_offsets,
        final_offsets_used_in_outer_evaluation=False,fits=fit_receipts,saved_model_replays=len(fit_receipts),
        protected_labels_read=False,new_independent_assessment=False,model_promoted=False,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()},frozen_counts=list(frozen)))


if __name__=='__main__':main()
