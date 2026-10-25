"""이중 제외 보정의 분리, 중앙값, 상한, 최종 예측을 별도로 재계산한다."""
import json
from itertools import combinations
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.two_winter import validate
from src.extended_search import temperature_gate
from scripts.evaluate_method_blending import preservation


def read(path):return json.loads(path.read_text('utf-8'))


def independent_offsets(frame,limit):
    actual=frame.road_temp.to_numpy(float);predicted=frame.prediction.to_numpy(float)
    valid=np.isfinite(actual)&np.isfinite(predicted)
    residual=actual[valid]-predicted[valid];stations=frame.station.to_numpy()[valid]
    assert len(residual)>0
    medians=[float(np.median(residual[stations==station])) for station in np.unique(stations)]
    return dict(pooled_median=max(-limit,min(limit,float(np.median(residual)))),
                station_median=max(-limit,min(limit,float(np.median(medians)))))


def main():
    folder=ROOT/'outputs/private/followup_offset_20261024_v1'
    out=ROOT/'outputs/private/followup_offset_audit_20261024_v1'
    if out.exists():raise FileExistsError('Preserve independent offset audit')
    plan=read(folder/'plan.json');config=plan['settings'];summary=read(folder/'summary.json')
    decisions=read(folder/'decisions.json');frozen=preservation()
    assert summary['status']=='nested_offset_comparison_complete' and summary['saved_model_replays']==6
    for name,expected in plan['signatures'].items():assert sha(ROOT/name)==expected,name
    for name,expected in summary['files'].items():assert sha(folder/name)==expected,name
    source=validate(pd.read_parquet(ROOT/config['data'],columns=['station','time','group','winter','road_temp','ice','asos_air_temp']))
    base=validate(pd.read_parquet(ROOT/config['reference']/'predictions.parquet'))
    saved=validate(pd.read_parquet(folder/'predictions.parquet'))
    pd.testing.assert_frame_equal(base,saved[base.columns],check_exact=True)
    groups=sorted(base.group.unique());parts={};fit_checks=[]
    for pair in combinations(groups,2):
        stem='__'.join(pair);record=read(folder/'models'/(stem+'.json'))
        prediction_path=folder/'models'/(stem+'.parquet');model_path=folder/'models'/(stem+'.joblib')
        assert sha(prediction_path)==record['prediction_sha256'] and sha(model_path)==record['model_sha256']
        assert record['excluded_groups']==list(pair)
        train=source.loc[~source.group.isin(pair)&source.road_temp.notna()&source.asos_air_temp.notna()]
        query=source.loc[source.group.isin(pair)].sort_values(['station','time']).reset_index(drop=True)
        assert record['training_stations']==sorted(train.station.unique()) and record['training_rows']==len(train)
        assert not set(train.station)&set(query.station)
        prediction=validate(pd.read_parquet(prediction_path))
        pd.testing.assert_frame_equal(prediction[query.columns],query,check_exact=True)
        assert np.array_equal(prediction.prediction.notna(),query.asos_air_temp.notna())
        parts[pair]=prediction
        fit_checks.append(dict(excluded_groups=list(pair),training_stations=record['training_stations'],
                              training_rows=len(train),prediction_rows=len(query),model_sha256=sha(model_path)))
    expected={policy:np.full(len(base),np.nan) for policy in config['policies']};checks=[]
    for outer in groups:
        residuals=[]
        for other in groups:
            if other==outer:continue
            part=parts[tuple(sorted([outer,other]))]
            residuals.append(part.loc[part.group.eq(other)])
        calibration=pd.concat(residuals,ignore_index=True)
        assert not calibration.group.eq(outer).any()
        correction=independent_offsets(calibration,config['maximum_absolute_offset_c'])
        recorded=decisions[outer]
        assert recorded['calibration_groups']==sorted(set(groups)-{outer})
        assert recorded['calibration_stations']==sorted(calibration.station.unique())
        assert recorded['calibration_valid_rows']==int((calibration.prediction.notna()&calibration.road_temp.notna()).sum())
        mask=base.group.eq(outer).to_numpy()
        for policy,value in correction.items():
            assert abs(value-recorded['offsets'][policy])<1e-12
            expected[policy][mask]=base.prediction.to_numpy()[mask]+value
        checks.append(dict(outer_group=outer,offsets=correction,calibration_rows=len(calibration),outer_outcomes_used=False))
    gate=read(ROOT/'config/followup_temperature_20261024.json')['temperature_gate']
    for policy,prediction in expected.items():
        np.testing.assert_allclose(prediction,saved[policy],atol=1e-12,rtol=0,equal_nan=True)
        measured=temperature_gate(base,prediction,base.prediction,gate)
        for key,value in measured.items():assert value==summary['reports'][policy][key],(policy,key)
    final=independent_offsets(base,config['maximum_absolute_offset_c'])
    assert final==summary['final_refit_offsets'] and summary['final_offsets_used_in_outer_evaluation'] is False
    assert preservation()==frozen
    receipt=dict(status='nested_offset_independently_verified',fits=fit_checks,outer_checks=checks,
        policies=config['policies'],prediction_rows=len(base),final_refit_offsets=final,
        plan_sha256=sha(folder/'plan.json'),summary_sha256=sha(folder/'summary.json'),
        predictions_sha256=sha(folder/'predictions.parquet'),audit_code_sha256=sha(Path(__file__)),
        protected_labels_read=False,new_independent_assessment=False,frozen_counts=list(frozen))
    out.mkdir(parents=True)
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('Nested offset audit verified',len(fit_checks),'fits',len(base),'rows',flush=True)


if __name__=='__main__':main()
