"""동일 4지역 제외·동일 온도 v3 설정에서 새 지표면 입력의 추가 가치를 비교한다."""
from datetime import datetime,timezone
from pathlib import Path
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.reanalysis_models import feature_table
from src.solar_memory_search import feature_table as solar_features
from src.extended_search import temperature_gate
from src.temperature_transfer import regression_report
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.fetch_reanalysis_inputs import read,write
from scripts.evaluate_objective_icing import verify_preserved


def main():
    config=ROOT/'config/reanalysis_temperature_20261031.json';plan=read(config);out=ROOT/plan['output']
    audit=read(ROOT/plan['input_audit']);assert audit['status']=='passed'
    data_path=ROOT/plan['data'];assert sha(data_path)==audit['data_sha256']
    inputs=[config,data_path,ROOT/plan['input_audit'],ROOT/plan['baseline'],Path(__file__),ROOT/'src/reanalysis_models.py',
            ROOT/'src/reanalysis_inputs.py',ROOT/'src/solar_memory_search.py',ROOT/'src/combined_thermal_history.py',
            ROOT/'src/thermal_extended.py',ROOT/'src/extended_search.py']
    signatures={p.relative_to(ROOT).as_posix():sha(p) for p in inputs}
    frozen=verify_preserved()
    if out.exists():assert read(out/'plan.json')['signatures']==signatures
    else:
        out.mkdir(parents=True)
        write(out/'plan.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),settings=plan,signatures=signatures,
            preservation=frozen,retrospective_only=True,new_independent_assessment=False))
    if (out/'summary.json').exists():raise FileExistsError('Preserve completed comparison')
    f=pd.read_parquet(data_path).sort_values(['station','time']).reset_index(drop=True)
    assert len(set(f.station))==23 and not set(f.station)&set(plan['blocked_stations'])
    baseline=pd.read_parquet(ROOT/plan['baseline']).sort_values(['station','time']).reset_index(drop=True)
    original_report=read((ROOT/plan['baseline']).parent/'report.json')
    np.testing.assert_allclose(regression_report(baseline,baseline.prediction)['pooled']['mae'],
                               original_report['regression']['pooled']['mae'],rtol=0,atol=1e-12)
    groups=sorted(set(f.group)-{'competition'});base=solar_features(f,'combined_asos_solar');reports={};fits=[]
    for candidate in plan['candidates']:
        folder=out/candidate;folder.mkdir(exist_ok=True);x=feature_table(f,candidate,base);parts=[]
        for held in groups:
            modelpath=folder/(held+'.joblib');predpath=folder/(held+'.parquet');recordpath=folder/(held+'.json')
            train=f.loc[f.group.ne(held)&f.road_temp.notna()&f.asos_air_temp.notna()];query=f.loc[f.group.eq(held)]
            assert not set(train.station)&set(query.station)
            if recordpath.exists():
                record=read(recordpath);assert sha(modelpath)==record['model_sha256'] and sha(predpath)==record['predictions_sha256']
                result=pd.read_parquet(predpath)
            else:
                if modelpath.exists() or predpath.exists():raise FileExistsError('Unrecorded model output; inspect before resuming')
                model=HistGradientBoostingRegressor(**plan['model']);started=time.perf_counter()
                with deny_network() as attempts,threadpool_limits(limits=plan['threads']):
                    model.fit(x.loc[train.index],train.road_temp.to_numpy())
                    predicted=model.predict(x.loc[query.index])
                assert not attempts and np.isfinite(predicted).all()
                result=query[['station','time','group','winter','ice','road_temp','asos_air_temp']].copy()
                result['prediction']=np.where(query.asos_air_temp.notna(),predicted,np.nan)
                result.to_parquet(predpath,index=False,compression='zstd');joblib.dump(model,modelpath,compress=3)
                record=dict(candidate=candidate,held=held,training_stations=sorted(train.station.unique()),training_rows=len(train),
                    features=list(x),parameters=model.get_params(),seconds=time.perf_counter()-started,
                    model_sha256=sha(modelpath),predictions_sha256=sha(predpath),protected_outcomes_used=False)
                write(recordpath,record)
            fits.append(record);parts.append(result)
            print('FIT',len(fits),'/8',candidate,held,round(record['seconds'],1),flush=True)
        result=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
        pd.testing.assert_frame_equal(result[['station','time','road_temp','ice']],baseline[['station','time','road_temp','ice']],check_exact=True)
        report=temperature_gate(result,result.prediction,baseline.prediction,plan['temperature_gate'])
        report['retrospective_only']=True
        result.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
        write(folder/'report.json',report);reports[candidate]=report
        print('RESULT',candidate,report['regression']['pooled'],report['gates'],flush=True)
    assert verify_preserved()==frozen
    write(out/'summary.json',dict(status='reanalysis_temperature_complete',fits=fits,reports=reports,
        baseline=regression_report(baseline,baseline.prediction),baseline_sha256=sha(ROOT/plan['baseline']),
        primary_candidate=plan['primary_candidate'],primary_success=reports[plan['primary_candidate']]['eligible'],
        retrospective_only=True,production_model_changed=False,new_independent_assessment=False,
        preservation=frozen,files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))


if __name__=='__main__':main()
