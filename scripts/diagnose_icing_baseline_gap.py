"""같은 입력 범위에서 기온 기준선과 현재 판정의 차이를 조건·날짜·지점별로 분해한다."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.two_winter import validate
from src.runtime_metrics import runtime_daily
from src.extended_comparison import event_retention
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    if out.exists() or not out.is_relative_to((ROOT/'outputs/private').resolve()):raise ValueError('New private output required')
    source=ROOT/'outputs/private/two_winter_models_20261024_v1/runtime_predictions.parquet'
    frozen=preservation();f=validate(pd.read_parquet(source)).sort_values(['station','time']).reset_index(drop=True)
    assert sha(source)==json.loads((source.parent/'audit_runtime.json').read_text('utf-8'))['runtime_prediction_sha256']
    valid=f.physical_both.notna();cold=f.temperature_both.le(0)
    dew=f.aws_dewpoint.ge(f.temperature_both);rain=f.rain15_max_3h.gt(0);snow=f.asos_snow_cm.gt(0)
    wet=dew|rain|snow;air=f.asos_air_temp.le(0)
    np.testing.assert_array_equal((cold&wet)[valid].to_numpy(int),f.physical_both[valid].to_numpy(int))
    methods={'current':f.physical_both.to_numpy(), 'asos_zero':np.where(valid,air,np.nan),
             'temperature_only':np.where(valid,cold,np.nan), 'air_with_water_gate':np.where(valid,air&wet,np.nan),
             'current_union_air':np.where(valid,(cold&wet)|air,np.nan), 'current_intersect_air':np.where(valid,cold&wet&air,np.nan)}
    reports={};days=[];stations=[]
    for name,pred in methods.items():
        report,st,day=runtime_daily(f,pred);events,detail=event_retention(f,pred,f.physical_both)
        reports[name]=dict(metrics=report,events=events);stations.append(st.assign(method=name));days.append(day.assign(method=name))
    daily=pd.concat(days,ignore_index=True);station=pd.concat(stations,ignore_index=True)
    counts=[]
    actual=f.ice.isin([0,1])&valid
    conditions={'both_alarm':air&cold&wet,'air_only_temperature':air&~cold,'air_only_water':air&cold&~wet,
                'current_only':~air&cold&wet,'neither':~(air|(cold&wet))}
    for (sid,winter),index in f.loc[actual].groupby(['station','winter']).groups.items():
        for label,condition in conditions.items():
            mask=f.index.isin(index)&condition.to_numpy();y=f.loc[mask,'ice']
            counts.append(dict(station=sid,winter=int(winter),category=label,rows=len(y),positive=int(y.eq(1).sum()),negative=int(y.eq(0).sum())))
    decomposition=[]
    for sid in sorted(f.station.unique()):
        a=daily.loc[daily.station.eq(sid)&daily.method.eq('asos_zero')]
        c=daily.loc[daily.station.eq(sid)&daily.method.eq('current')]
        av=a.loc[a.included_f1,'f1'];cv=c.loc[c.included_f1,'f1']
        na,nc=len(av),len(cv);sa,sc=float(av.sum()),float(cv.sum());ia=1/na if na else 0;ic=1/nc if nc else 0
        numerator=.5*(sc-sa)*(ia+ic);denominator=.5*(sc+sa)*(ic-ia)
        delta=sc*ic-sa*ia
        assert np.isclose(numerator+denominator,delta,atol=1e-14)
        decomposition.append(dict(station=sid,asos_active_days=na,current_active_days=nc,asos_f1=sa*ia,current_f1=sc*ic,
                                  delta_f1=delta,numerator_effect=numerator,active_day_denominator_effect=denominator))
    table=pd.DataFrame(decomposition)
    assert np.isclose(table.delta_f1.mean(),reports['current']['metrics']['f1_fixed_population']-reports['asos_zero']['metrics']['f1_fixed_population'])
    out.mkdir(parents=True);pd.DataFrame(counts).to_csv(out/'rule_disagreements.csv',index=False)
    table.to_csv(out/'daily_denominator_decomposition.csv',index=False);daily.to_csv(out/'daily.csv',index=False);station.to_csv(out/'stations.csv',index=False)
    assert preservation()==frozen
    result=dict(status='baseline_gap_decomposed',reports=reports,
        disagreement_totals=pd.DataFrame(counts).groupby('category')[['rows','positive','negative']].sum().to_dict('index'),
        decomposition=table.to_dict('records'),protected_labels_read=False,labels_changed=False,
        diagnostic_counterfactuals_not_adopted=True,source_sha256=sha(source),script_sha256=sha(Path(__file__)),frozen_counts=list(frozen))
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    print(json.dumps(dict(f1={k:v['metrics']['f1_fixed_population'] for k,v in reports.items()},disagreements=result['disagreement_totals'],decomposition=result['decomposition']),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
