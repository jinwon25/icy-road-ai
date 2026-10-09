"""고정 8지점을 함께 재표집하는 7일 블록의 짝지은 변화 구간을 계산한다."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,sys
import numpy as np,pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.audit_joint_surface import read,sha
from scripts.fresh_station_validation import DEFAULT_OUT,PRIVATE,verify_seal

PLAN=dict(seed=20261009,replicates=2000,block_days=7,interval_percentiles=[2.5,97.5],
          scope='Descriptive paired temporal block bootstrap conditional on eight fixed stations. All stations use the same sampled week blocks. Not a future-winter guarantee, unseen-station interval, significance claim or selection rule.',
          blocks='Nonoverlapping seven-day blocks from Nov1; final one-day tail is retained as a shorter block. Draw the same number of blocks with replacement; metrics retain their paired observed-row denominators.',
          delta_sign='Candidate minus original: F1 positive is better; FP/FN/temperature MAE negative is better.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',type=Path,default=DEFAULT_OUT);parser.add_argument('--plan-only',action='store_true');args=parser.parse_args();out=args.experiment.resolve()
    if not out.is_relative_to(PRIVATE.resolve()):parser.error('Private experiment required')
    if args.plan_only:
        target=out/'uncertainty_plan.json'
        if target.exists():raise FileExistsError('Preserve plan')
        target.write_text(json.dumps(dict(PLAN,recorded_at_utc=datetime.now(timezone.utc).isoformat()),ensure_ascii=False,indent=2),'utf-8');return
    verify_seal(out);audit=read(out/'independent_verification.json')
    assert audit['status'] in {'passed','passed_with_collection_interval_deviation'} and audit['metrics_reproduced'] is True
    target=out/'temporal_uncertainty.json'
    if target.exists():raise FileExistsError('Preserve intervals')
    plan=read(out/'uncertainty_plan.json');assert {k:plan[k] for k in PLAN}==PLAN
    d=pd.read_parquet(out/'evaluation.parquet');d['block']=((d.time.dt.normalize()-pd.Timestamp('2024-11-01')).dt.days//plan['block_days']).astype(int)
    stations=sorted(d.station.unique());blocks=sorted(d.block.unique());counts=np.zeros((len(blocks),2,3));errors=np.zeros((len(blocks),len(stations),3))
    for b,part in d.groupby('block'):
        valid=part.ice.notna();y=part.loc[valid,'ice'].to_numpy()
        for j,p in enumerate(['original_ice','thermal_moisture']):
            predicted=part.loc[valid,p].to_numpy();counts[b,j]=[((y==1)&(predicted==1)).sum(),((y==0)&(predicted==1)).sum(),((y==1)&(predicted==0)).sum()]
        for j,st in enumerate(stations):
            q=part[part.station.eq(st)];valid=np.isfinite(q.road_temp)&np.isfinite(q.original_weather_ridge)&np.isfinite(q.weather_hgb23)
            errors[b,j]=[np.abs(q.loc[valid,'original_weather_ridge']-q.loc[valid,'road_temp']).sum(),np.abs(q.loc[valid,'weather_hgb23']-q.loc[valid,'road_temp']).sum(),valid.sum()]
    def delta(c,e):
        den=2*c[:,0]+c[:,1]+c[:,2];f=np.divide(2*c[:,0],den,out=np.full(2,np.nan),where=den>0)
        valid=e[:,2]>0;mae=np.mean((e[valid,1]-e[valid,0])/e[valid,2]) if valid.any() else np.nan
        return dict(f1_delta=f[1]-f[0],fp_delta=c[1,1]-c[0,1],fn_delta=c[1,2]-c[0,2],station_macro_mae_delta=mae)
    point=delta(counts.sum(axis=0),errors.sum(axis=0));rng=np.random.default_rng(plan['seed']);samples=[]
    for _ in range(plan['replicates']):
        sample=rng.integers(0,len(blocks),len(blocks));samples.append(delta(counts[sample].sum(axis=0),errors[sample].sum(axis=0)))
    f=pd.DataFrame(samples);intervals={}
    for k,v in point.items():
        q=f[k].dropna();lo,hi=np.percentile(q,plan['interval_percentiles']) if len(q) else (np.nan,np.nan)
        intervals[k]=dict(point=float(v) if np.isfinite(v) else None,lower=float(lo) if np.isfinite(lo) else None,upper=float(hi) if np.isfinite(hi) else None,defined_replicates=len(q))
    result=dict(plan=plan,blocks=len(blocks),stations=len(stations),intervals=intervals,evaluation_sha256=sha(out/'evaluation.parquet'),source_sha256=sha(__file__),computed_at_utc=datetime.now(timezone.utc).isoformat())
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),'utf-8');print(json.dumps(intervals),flush=True)


if __name__=='__main__':main()
