"""단순 보정 기준선의 학습 중앙값 조건·추론·지표·날짜 민감도를 검산한다."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_objective_icing import read,write,verify_preserved
from scripts.audit_road_weather_transfer import measure,compare


def main():
    out=ROOT/'outputs/private/weather_calibration_controls_20261031_v1'
    destination=out/'independent_verification.json'
    if destination.exists():raise FileExistsError('Preserve calibration audit')
    plan=read(out/'plan.json');settings=plan['settings'];summary=read(out/'summary.json')
    for p,h in plan['signatures'].items():assert sha(ROOT/p)==h,p
    for p,h in summary['files'].items():assert sha(out/p)==h,p
    f=pd.read_parquet(ROOT/settings['input']).sort_values(['station','time']).reset_index(drop=True)
    constants=pd.read_csv(out/'training_constants.csv');checks=0;replayed=0;resampled=0
    for target,result in summary['reports'].items():
        field=dict(air_temperature='air_temp',relative_humidity='humidity',wind_speed='wind_speed')[target]
        a=f['asos_'+field].where((f.asos_age_minutes>0)&(f.asos_age_minutes<=60)).to_numpy()
        b=f['aws_'+field].where((f.aws_age_minutes>0)&(f.aws_age_minutes<=15)).to_numpy()
        b=np.where(np.isfinite(b),b,a);good=f[target].notna().to_numpy()&np.isfinite(a)&np.isfinite(b)
        saved=pd.read_parquet(out/target/'predictions.parquet')
        original=pd.read_parquet(ROOT/settings['study']/target/'predictions.parquet')
        pd.testing.assert_frame_equal(saved[original.columns],original,check_exact=True)
        for row in constants.loc[constants.target.eq(target)].itertuples():
            train=f.loc[f.group.ne(row.held)&good];assert len(train)==row.training_rows
            count=train.groupby(['station','winter']).station.transform('size').to_numpy();weight=1/count
            y=train[target].to_numpy();delta=y-b[train.index]
            for values,median in [(y,row.training_median),(delta,row.residual_offset)]:
                # 중간값 정의의 좌·우 가중 분포 조건을 직접 확인한다.
                assert weight[values<median-1e-12].sum()<=weight.sum()/2+1e-10
                assert weight[values<=median+1e-12].sum()>=weight.sum()/2-1e-10
                assert np.isclose(values,median,rtol=0,atol=1e-12).any();checks+=3
            q=saved.loc[saved.group.eq(row.held)]
            for c,value in [('weighted_training_median',np.full(len(q),row.training_median)),
                            ('weighted_residual_offset',q.aws_fallback.to_numpy()+row.residual_offset)]:
                if target=='relative_humidity':value=np.clip(value,0,100)
                if target=='wind_speed':value=np.maximum(value,0)
                np.testing.assert_allclose(value,q[c],atol=1e-12,rtol=0);replayed+=len(q)
        for c,record in result['metrics'].items():
            actual=dict(pooled=measure(saved,c),regions={k:measure(q,c) for k,q in saved.groupby('group')},
                        winters={str(k):measure(q,c) for k,q in saved.groupby('winter')})
            checks+=compare(actual,record)
        bs=settings['bootstrap']
        for control in settings['controls']:
            totals=[];counts=[]
            for year in [2024,2025]:
                q=saved.loc[saved.winter.eq(year)].copy();q['date']=q.time.dt.normalize()
                q['delta']=abs(q.residual_hgb-q.observed)-abs(q[control]-q.observed)
                daily=q.groupby('date').agg(delta=('delta','sum'),n=('delta','size'))
                daily=daily.reindex(pd.date_range(f'{year}-11-01',f'{year+1}-02-28'),fill_value=0).to_numpy()
                starts=np.random.default_rng(bs['seed']+year-2024).integers(0,120,(2000,18))
                ids=np.concatenate([(starts+j)%120 for j in range(7)],axis=1)
                # concatenate 는 블록 순서를 다르게 만들므로 명시적인 행별 블록 전개로 정렬한다.
                ids=np.array([[(int(start)+j)%120 for start in row for j in range(7)][:120] for row in starts])
                sampled=daily[ids].sum(axis=1);totals.append(sampled[:,0]);counts.append(sampled[:,1])
            values=sum(totals)/sum(counts)
            np.testing.assert_allclose(values,np.load(out/target/(control+'_bootstrap.npy')),atol=1e-12,rtol=0);resampled+=len(values)
            expected=result['bootstrap'][control]
            checks+=compare(np.quantile(values,[.025,.5,.975]).tolist(),expected['quantile025_50_975'])
            c=result['metrics']['residual_hgb'];bmetrics=result['metrics'][control]
            gates=dict(overall=c['pooled']['mae']<bmetrics['pooled']['mae'],
                winters=all(c['winters'][y]['mae']<v['mae'] for y,v in bmetrics['winters'].items()),
                date_block_upper=float(np.quantile(values,.975))<0)
            checks+=compare(gates,result['checks'][control])
        assert result['supplement_eligible']==all(all(v.values()) for v in result['checks'].values())
    assert summary['selected_targets']==[t for t,r in summary['reports'].items() if r['supplement_eligible']]
    assert verify_preserved()==plan['preservation']
    write(destination,dict(status='passed',summary_sha256=sha(out/'summary.json'),constant_folds=len(constants),
        replay_values=replayed,checks=checks,bootstrap_values=resampled,audit_source_sha256=sha(Path(__file__))))
    print('CALIBRATION AUDIT PASSED',checks,replayed,resampled,flush=True)


if __name__=='__main__':main()
