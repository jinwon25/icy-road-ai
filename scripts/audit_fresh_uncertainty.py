"""별도 블록 집계로 고정 8지점의 짝지은 시간 재표집 구간을 검산한다."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,sys
import numpy as np,pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.fresh_station_validation import DEFAULT_OUT,PRIVATE,verify_seal
from src.research_delivery import file_sha


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',type=Path,default=DEFAULT_OUT);args=parser.parse_args();out=args.experiment.resolve()
    if not out.is_relative_to(PRIVATE.resolve()):parser.error('Private experiment required')
    verify_seal(out);path=out/'temporal_uncertainty.json';result=json.loads(path.read_text('utf-8'));plan=result['plan']
    target=out/'uncertainty_verification.json'
    if target.exists():raise FileExistsError('Preserve verification')
    assert result['evaluation_sha256']==file_sha(out/'evaluation.parquet')
    d=pd.read_parquet(out/'evaluation.parquet');d['week']=((d.time.dt.normalize()-pd.Timestamp('2024-11-01')).dt.days//plan['block_days']).astype(int)
    blocks=sorted(d.week.unique());stations=sorted(d.station.unique());metrics={}
    for policy in ['original_ice','thermal_moisture']:
        valid=d.ice.notna();y=d.ice.eq(1);p=d[policy].eq(1)
        counts=pd.DataFrame(dict(week=d.week,tp=valid&y&p,fp=valid&~y&p,fn=valid&y&~p)).groupby('week').sum().reindex(blocks)
        metrics[policy]=counts.to_numpy(dtype=float)
    valid=np.isfinite(d.road_temp)&np.isfinite(d.original_weather_ridge)&np.isfinite(d.weather_hgb23)
    errors=d.loc[valid,['week','station']].copy()
    errors['original']=(d.loc[valid,'original_weather_ridge']-d.loc[valid,'road_temp']).abs()
    errors['candidate']=(d.loc[valid,'weather_hgb23']-d.loc[valid,'road_temp']).abs();errors['n']=1
    cells=pd.MultiIndex.from_product([blocks,stations],names=['week','station'])
    sums=errors.groupby(['week','station'])[['original','candidate','n']].sum().reindex(cells,fill_value=0).to_numpy().reshape(len(blocks),len(stations),3)
    def values(indices):
        m={k:v[indices].sum(axis=0) for k,v in metrics.items()};f={k:2*v[0]/(2*v[0]+v[1]+v[2]) if 2*v[0]+v[1]+v[2] else np.nan for k,v in m.items()}
        e=sums[indices].sum(axis=0);present=e[:,2]>0
        return dict(f1_delta=f['thermal_moisture']-f['original_ice'],fp_delta=m['thermal_moisture'][1]-m['original_ice'][1],fn_delta=m['thermal_moisture'][2]-m['original_ice'][2],station_macro_mae_delta=float(np.mean((e[present,1]-e[present,0])/e[present,2])) if present.any() else np.nan)
    point=values(np.arange(len(blocks)));rng=np.random.default_rng(plan['seed'])
    samples=pd.DataFrame([values(rng.integers(0,len(blocks),len(blocks))) for _ in range(plan['replicates'])])
    for key,expected in result['intervals'].items():
        q=samples[key].dropna();assert len(q)==expected['defined_replicates']
        lo,hi=np.percentile(q,plan['interval_percentiles']) if len(q) else (np.nan,np.nan)
        for actual,stored in [(point[key],expected['point']),(lo,expected['lower']),(hi,expected['upper'])]:
            if stored is None:assert not np.isfinite(actual)
            else:np.testing.assert_allclose(actual,stored,rtol=0,atol=1e-12)
    receipt=dict(status='passed',checked_at_utc=datetime.now(timezone.utc).isoformat(),blocks=len(blocks),stations=len(stations),replicates=plan['replicates'],intervals_sha256=file_sha(path),source_sha256=file_sha(__file__),independent_block_aggregation=True)
    target.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
