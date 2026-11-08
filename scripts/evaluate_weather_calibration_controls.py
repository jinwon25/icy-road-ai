"""기상 HGB의 개선을 학습 상수·잔차 상수와 비교한다. 적합 설정을 바꾸지 않는다."""
from datetime import datetime,timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.road_weather_transfer import baselines,balanced_weights,constrain
from scripts.evaluate_road_weather_transfer import report,bootstrap
from scripts.evaluate_objective_icing import read,write,verify_preserved
from src.data_source import sha256_file as sha


def weighted_median(values,weights):
    order=np.argsort(values,kind='stable');v=np.asarray(values)[order];w=np.asarray(weights)[order]
    if len(v)==0 or not np.isfinite(v).all() or not np.isfinite(w).all() or (w<=0).any():
        raise ValueError('Finite values and positive weights required')
    return float(v[np.searchsorted(np.cumsum(w),.5*np.sum(w),side='left')])


def main():
    cfg=ROOT/'config/weather_calibration_controls_20261031.json';plan=read(cfg);out=ROOT/plan['output'];study=ROOT/plan['study']
    if out.exists():raise FileExistsError('Preserve calibration controls')
    summary=read(study/'summary.json');audit=read(study/'independent_verification.json')
    assert audit['status']=='passed' and audit['summary_sha256']==sha(study/'summary.json')
    frozen=verify_preserved();out.mkdir(parents=True)
    write(out/'plan.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),settings=plan,preservation=frozen,
        signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [cfg,Path(__file__),ROOT/plan['input'],study/'summary.json',study/'independent_verification.json']}))
    f=pd.read_parquet(ROOT/plan['input']).sort_values(['station','time']).reset_index(drop=True)
    results={};constants=[]
    for target in summary['reports']:
        p=pd.read_parquet(study/target/'predictions.parquet');a,b=baselines(f,target)
        good=f[target].notna().to_numpy()&np.isfinite(a)&np.isfinite(b)
        for held in sorted(p.group.unique()):
            train=f.loc[f.group.ne(held)&good];w=balanced_weights(train);q=p.group.eq(held)
            values=train[target].to_numpy();median=weighted_median(values,w);offset=weighted_median(values-b[train.index],w)
            p.loc[q,'weighted_training_median']=constrain(np.full(q.sum(),median),target)
            p.loc[q,'weighted_residual_offset']=constrain(p.loc[q,'aws_fallback'].to_numpy()+offset,target)
            constants.append(dict(target=target,held=held,training_rows=len(train),training_median=median,residual_offset=offset))
        folder=out/target;folder.mkdir();p.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
        metrics={c:report(p,c) for c in ['residual_hgb']+plan['controls']};sensitivities={};checks={}
        for control in plan['controls']:
            q=p.copy();q['aws_fallback']=q[control]
            sensitivity,samples=bootstrap(q,'residual_hgb',dict(bootstrap=plan['bootstrap']|{'interpretation':'fixed four development regions; calendar sensitivity only'}))
            sensitivities[control]=sensitivity;np.save(folder/(control+'_bootstrap.npy'),samples,allow_pickle=False)
            candidate=metrics['residual_hgb'];base=metrics[control]
            checks[control]=dict(overall=candidate['pooled']['mae']<base['pooled']['mae'],
                winters=all(candidate['winters'][y]['mae']<m['mae'] for y,m in base['winters'].items()),
                date_block_upper=sensitivity['quantile025_50_975'][2]<0)
        results[target]=dict(metrics=metrics,bootstrap=sensitivities,checks=checks,
            supplement_eligible=all(all(c.values()) for c in checks.values()) and summary['reports'][target]['primary_success'])
        print('CONTROL',target,{c:m['pooled']['mae'] for c,m in metrics.items()},checks,flush=True)
    assert verify_preserved()==frozen
    pd.DataFrame(constants).to_csv(out/'training_constants.csv',index=False,encoding='utf-8-sig')
    write(out/'summary.json',dict(status='weather_calibration_controls_complete',reports=results,
        selected_targets=[t for t,r in results.items() if r['supplement_eligible']],preservation=frozen,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))


if __name__=='__main__':main()
