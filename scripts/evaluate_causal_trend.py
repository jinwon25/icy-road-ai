"""새 모델 학습 없이 관측 지연 보정의 고정 정책과 지역 내부 선택을 비교한다."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.weather_information import past_hour_trend,extrapolated_temperature
from src.residual_icing import select
from src.additive_icing import metric_table
from src.blind_icing import daily_metrics,summarize_days,event_table
from src.data_source import sha256_file as sha
from scripts.blind_icing_validation import DEFAULT,verify,read,write,now,old_freezes
from scripts.audit_icing_transition import independent_metrics,independent_events


def main():
    cfg=ROOT/'config/causal_trend_20261025.json';plan=read(cfg);out=ROOT/plan['out']
    if out.exists():raise FileExistsError('Preserve prior experiment')
    verify(DEFAULT);f=pd.read_parquet(ROOT/plan['source']).sort_values(['station','time']).reset_index(drop=True)
    assert len(set(f.station))==23 and set(f.station).isdisjoint(plan['blocked_stations'])
    out.mkdir(parents=True)
    write(out/'plan.json',dict(at_utc=now(),settings=plan,signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [cfg,Path(__file__),ROOT/'src/weather_information.py',ROOT/'src/residual_icing.py',ROOT/'src/additive_icing.py',ROOT/plan['source']]}))
    trend=past_hour_trend(f[['station','time','asos_source_time','asos_air_temp','asos_age_minutes']]);f=pd.concat([f,trend],axis=1)
    f=f.loc[~f.group.eq('competition')].copy();assert len(set(f.station))==9
    specs=[dict(candidate='asos_zero',alpha=0.,cap=0.,rounds=0,complexity=0)]
    for alpha in plan['alphas']:
        for cap in plan['caps_c']:specs.append(dict(candidate=f'trend_a{alpha:g}_c{cap:g}',alpha=alpha,cap=cap,rounds=0,complexity=1))
    for spec in specs:
        estimate=f.asos_air_temp if spec['alpha']==0 else extrapolated_temperature(f.asos_air_temp,f.asos_age_minutes,f.trend_c_per_hour,spec['alpha'],spec['cap'])
        f[spec['candidate']]=np.where(f.available,np.asarray(estimate)<=0,np.nan)
    selections=[]
    for held in sorted(f.group.unique()):
        inner=f.loc[~f.group.eq(held)];table=metric_table(inner,inner[[s['candidate'] for s in specs]].to_numpy(),specs);path=out/(held+'__inner.csv');table.to_csv(path,index=False)
        chosen={track:select(table,track=='guarded') for track in ['guarded','maximum_f1']}
        selections.append(dict(held=held,selected=chosen,inner_sha256=sha(path)))
        for track,name in chosen.items():f.loc[f.group.eq(held),track]=f.loc[f.group.eq(held),name]
    write(out/'selection.json',dict(at_utc=now(),selections=selections,outer_metrics_computed=False))
    f.to_parquet(out/'predictions.parquet',index=False,compression='zstd');reports={};checks=0;pop=sorted(f.station.unique())
    for name in [s['candidate'] for s in specs]+['guarded','maximum_f1']:
        r=summarize_days(daily_metrics(f,f[name],pop,plan['winters']),pop);other=independent_metrics(f,f[name]);e,events=event_table(f,f[name],f.asos_zero)
        for k in ['f1_fixed_population','precision_available_station_mean','recall_available_station_mean','tp','fp','fn']:
            np.testing.assert_allclose(r[k],other[k],atol=1e-12,rtol=0);checks+=1
        assert e==independent_events(f,f[name],f.asos_zero)
        report=dict(all=r,events=e,winters={},regions={})
        for year in [2024,2025]:
            q=f.loc[f.winter.eq(year)];report['winters'][str(year)]=summarize_days(daily_metrics(q,q[name],pop,[w for w in plan['winters'] if w[0].startswith(str(year))]),pop)
        for group,q in f.groupby('group'):
            local=sorted(q.station.unique());report['regions'][group]=summarize_days(daily_metrics(q,q[name],local,plan['winters']),local)
        reports[name]=report
    b=reports['asos_zero'];c=reports['guarded']
    gates=dict(f1=c['all']['f1_fixed_population']>b['all']['f1_fixed_population'] and c['all']['f1_fixed_population']>=1.01*b['all']['f1_fixed_population'],
        precision=c['all']['precision_available_station_mean']>=b['all']['precision_available_station_mean'],recall=c['all']['recall_available_station_mean']>=b['all']['recall_available_station_mean'],
        winters=all(c['winters'][k]['f1_fixed_population']>=b['winters'][k]['f1_fixed_population'] for k in b['winters']),
        regions=all(c['regions'][k]['f1_fixed_population']>=b['regions'][k]['f1_fixed_population'] for k in b['regions']),
        stations=all(c['all']['station_f1_fixed'][s]>=b['all']['station_f1_fixed'][s] for s in pop),events=c['events']['lost_events']==0)
    verify(DEFAULT);assert old_freezes()==(47,549)
    write(out/'summary.json',dict(status='causal_trend_development_complete',at_utc=now(),selections=selections,reports=reports,primary_gates=gates,primary_success=all(gates.values()),
        trend_available_rows=int((f.available&f.trend_available).sum()),available_rows=int(f.available.sum()),metric_checks=checks,event_checks=len(reports),predictions_sha256=sha(out/'predictions.parquet'),new_four_site_outcomes_used=False,production_model_changed=False))
    print('COMPLETE',len(specs),'policies',gates,flush=True)


if __name__=='__main__':main()
