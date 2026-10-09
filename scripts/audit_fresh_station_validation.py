"""새 지점 검증의 예측 봉인·원천 정답·지표를 별도로 재계산한다."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, sys
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.audit_joint_surface import read,sha,identity,close,report
from scripts.fresh_station_validation import verify_seal,old_freezes,SOURCE,PRIVATE,DEFAULT_OUT
from scripts.baseline_ice_logistic import FEATURES
from src.validation import normalize_state


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',type=Path,default=DEFAULT_OUT);parser.add_argument('--predictions-only',action='store_true');args=parser.parse_args();out=args.experiment.resolve()
    if not out.is_relative_to(PRIVATE.resolve()):parser.error('Private experiment required')
    destination=out/('prediction_audit.json' if args.predictions_only else 'independent_verification.json')
    if destination.exists():raise FileExistsError('Preserve existing audit')
    seal=verify_seal(out);plan=read(out/'plan.json');fit=read(out/'fit_receipt.json')
    index=pd.read_parquet(PRIVATE/'ice_group_balanced_20261009_v1/development_index.parquet');raw=pd.read_parquet(PRIVATE/'ice_group_balanced_20261009_v1/feature_matrix.parquet');temp=pd.read_parquet(PRIVATE/'weather_fallback_20261009_v1/training_index.parquet')
    assert index.time.ge('2024-11-01').all() and index.time.lt('2025-03-01').all()
    assert not set(index.station)&{'12410','33411','23402'}
    assert len(set(index.station))==23
    pd.testing.assert_frame_equal(index[['station','time']],temp[['station','time']])
    mask=np.isfinite(temp.road_temp)&raw.asos_air_temp.notna()
    assert fit['training_identity']==identity(temp.loc[mask,['station','time','road_temp']])
    assert fit['training_rows']==int(mask.sum()) and fit['training_stations']==sorted(set(index.loc[mask,'station']))
    hgb=joblib.load(out/'weather_hgb23.joblib');assert sha(out/'weather_hgb23.joblib')==fit['model_sha256']
    assert list(hgb.feature_names_in_)==FEATURES
    clone=HistGradientBoostingRegressor(**fit['parameters'])
    with threadpool_limits(limits=2):clone.fit(raw.loc[mask,FEATURES],temp.loc[mask,'road_temp'])
    ice_info=read(SOURCE/'external_augmentation_nested_v1/baseline/fit_manifest.json')
    ice=joblib.load(SOURCE/'external_augmentation_nested_v1/baseline/model.joblib');ridge=joblib.load(SOURCE/'external_temperature_nested_v1/baseline/model.joblib')
    predictions=pd.read_parquet(out/'predictions.parquet');assert not predictions.duplicated(['station','time']).any()
    assert not {'ice','state_raw','road_temp'}&set(predictions)
    grid=pd.date_range(plan['development_start_kst'],pd.Timestamp(plan['development_end_kst'])+pd.Timedelta(days=1),freq='10min',inclusive='left')
    expected={s:g for g,stations in plan['station_groups'].items() for s in stations}
    assert set(predictions.station)==set(expected) and not set(expected)&set(index.station)
    for station,group in expected.items():
        q=predictions.loc[predictions.station.eq(station)].reset_index(drop=True);x=pd.read_parquet(out/f'inputs_{station}.parquet')
        assert pd.DatetimeIndex(q.time).equals(grid) and q.group.eq(group).all()
        assert not {'ice','state_raw','road_temp'}&set(x)
        pd.testing.assert_frame_equal(q[['station','time']],x[['station','time']])
        for prefix in ['aws','asos']:
            age=x[prefix+'_age_minutes'];assert age.dropna().between(0,60).all()
            assert (x.loc[x[prefix+'_source_time'].notna(),prefix+'_source_time']<x.loc[x[prefix+'_source_time'].notna(),'time']).all()
        with threadpool_limits(limits=2):
            t=np.where(x.asos_air_temp.notna(),hgb.predict(x[FEATURES]),np.nan)
            t2=np.where(x.asos_air_temp.notna(),clone.predict(x[FEATURES]),np.nan)
            base_t=np.where(x.asos_air_temp.notna(),ridge.predict(x[FEATURES]),np.nan)
            score=ice.predict_proba(x[ice_info['features']])[:,1]
        np.testing.assert_allclose(t,t2,rtol=0,atol=0,equal_nan=True)
        np.testing.assert_allclose(q.weather_hgb23,t,rtol=0,atol=0,equal_nan=True)
        np.testing.assert_allclose(q.original_weather_ridge,base_t,rtol=0,atol=0,equal_nan=True)
        np.testing.assert_allclose(q.original_ice_score,score,rtol=0,atol=0)
        original=(score>=ice_info['threshold']).astype(int);np.testing.assert_array_equal(q.original_ice,original)
        wet=(x.aws_dewpoint.to_numpy()>=t)|(x.rain15_max_3h.to_numpy()>0)|(x.asos_snow_cm.to_numpy()>0)
        fallback=~np.isfinite(t)|x[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].isna().all(axis=1).to_numpy()
        np.testing.assert_array_equal(q.moisture_evidence,wet);np.testing.assert_array_equal(q.fallback,fallback)
        np.testing.assert_array_equal(q.thermal_moisture,np.where(fallback,original,(t<=0)&wet).astype(int))
    audit=dict(status='passed',checked_at_utc=datetime.now(timezone.utc).isoformat(),prediction_rows=len(predictions),stations=len(expected),
               seal_sha256=sha(out/'prediction_seal.json'),new_outcomes_present=(out/'download_manifest.json').exists(),temperature_refit_exact=True)
    if args.predictions_only:
        assert audit['new_outcomes_present'] is False
    else:
        first=read(out/'prediction_audit.json');manifest=read(out/'download_manifest.json');summary=read(out/'summary.json');evaluation=pd.read_parquet(out/'evaluation.parquet')
        assert seal['sealed_at_utc']<first['checked_at_utc']<manifest['first_request_utc']<=manifest['completed_at_utc']<summary['evaluated_at_utc']
        assert sha(out/'evaluation.parquet')==summary['evaluation_sha256']
        interval_checks=[]
        for run in out.glob('collection_run_*'):
            receipt=read(run/'receipt.json');assert sha(run/'collector_source.py')==receipt['source_sha256']
            assert receipt['workers']<=3 and receipt['global_minimum_request_interval_seconds']>=1.2
            assert sha(run/'request_start_intervals.json')==receipt['request_start_intervals_sha256']
            intervals=np.asarray(read(run/'request_start_intervals.json'),dtype=float)
            assert np.isfinite(intervals).all() and (intervals>0).all()
            minimum=receipt['global_minimum_request_interval_seconds']
            interval_checks.append(dict(run=run.name,timer=receipt.get('timer','monotonic without post-sleep recheck'),
                                        intervals=len(intervals),minimum_observed_seconds=float(intervals.min()) if len(intervals) else None,
                                        below_configured_minimum=int((intervals<minimum-1e-6).sum()),
                                        compliant=bool((intervals>=minimum-1e-6).all())))
        frames=[]
        for identifier,r in manifest['records'].items():
            p=out/'observations'/(identifier+'.parquet');assert sha(p)==r['sha256'];d=pd.read_parquet(p)
            assert set(d.station)<=set(expected) and set(d.station)<={r['station']}
            assert d.time.between(pd.Timestamp(r['start_kst']),pd.Timestamp(r['end_kst'])).all()
            np.testing.assert_allclose(d.ice,d.state_raw.map(normalize_state),rtol=0,atol=0,equal_nan=True)
            for transport in r['transport']:
                assert sha(out/'transport'/transport['transport_cache_path'])==transport['transport_response_sha256']
            frames.append(d)
        raw_y=pd.concat(frames,ignore_index=True);assert not raw_y.duplicated(['station','time']).any()
        merged=predictions.merge(raw_y[['station','time','ice','state_raw','road_temp','lat','lon','elevation_m']],on=['station','time'],how='left',validate='one_to_one',indicator=True)
        pd.testing.assert_frame_equal(merged,evaluation)
        for policy in plan['frozen_policies']:
            actual,_=report(evaluation,evaluation[policy]);assert actual.keys()==summary['metrics'][policy].keys()
            for k,v in actual.items():close(v,summary['metrics'][policy][k])
        for policy in plan['temperature_comparison']:
            valid=np.isfinite(evaluation.road_temp)&np.isfinite(evaluation[policy]);stations={}
            def regression(y,p):
                e=np.asarray(p)-np.asarray(y)
                if not len(e):return dict(n=0,mae=None,rmse=None,bias=None)
                return dict(n=len(e),mae=float(np.abs(e).mean()),rmse=float(np.sqrt((e*e).mean())),bias=float(e.mean()))
            pooled=regression(evaluation.loc[valid,'road_temp'],evaluation.loc[valid,policy])
            for st in sorted(evaluation.station.unique()):
                part=evaluation[valid&evaluation.station.eq(st)];stations[st]=regression(part.road_temp,part[policy])
            assert set(stations)==set(summary['temperature'][policy]['stations'])
            for k,v in pooled.items():close(v,summary['temperature'][policy]['pooled'][k])
            for st,r in stations.items():
                for k,v in r.items():close(v,summary['temperature'][policy]['stations'][st][k])
            active=[r for r in stations.values() if r['n']]
            assert summary['temperature'][policy]['stations_with_valid_temperature']==len(active)
            for k in ['mae','rmse','bias']:close(float(np.mean([r[k] for r in active])) if active else None,summary['temperature'][policy]['station_macro'][k])
        b=summary['metrics']['original_ice'];c=summary['metrics']['thermal_moisture'];assert summary['joint_fp_fn_improvement']==(c['fp']<b['fp'] and c['fn']<b['fn'])
        interval_compliant=all(r['compliant'] for r in interval_checks)
        audit.update(status='passed' if interval_compliant else 'passed_with_collection_interval_deviation',
                     outcome_rows=len(raw_y),evaluation_rows=len(evaluation),metrics_reproduced=True,summary_sha256=sha(out/'summary.json'),
                     collection_interval_compliant=interval_compliant,collection_interval_checks=interval_checks,
                     chronology_and_outcome_boundary_passed=True,
                     collection_deviation_interpretation='Original request records preserved. A shorter self-imposed collection interval is a disclosed protocol deviation; metric and chronology verification are separate. No model promotion.')
    original,reserved=old_freezes();audit.update(original_frozen_files=original,reserved_frozen_files=reserved,source_sha256=sha(__file__))
    destination.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(audit,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
