"""새 모델 선택 없이 결빙의 분포·오경보 진단표를 다른 구현으로 검산한다."""
from collections import Counter
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.two_winter import validate
from scripts.evaluate_method_blending import preservation


def read(path):return json.loads(path.read_text('utf-8'))


def main():
    private=ROOT/'outputs/private';study=private/'icing_state_memory_20261024_v1'
    out=private/'followup_failure_diagnostics_20261024_v1'
    if out.exists():raise FileExistsError('Preserve failure diagnostic audit')
    config=read(ROOT/'config/icing_state_memory_20261024.json');source=ROOT/config['baseline']
    assert sha(source)==read(source.parent/'audit_runtime.json')['runtime_prediction_sha256']
    frozen=preservation()
    frame=validate(pd.read_parquet(source,columns=['station','time','winter','ice','road_temp','physical_both']))
    valid=frame.ice.isin([0,1])&np.isfinite(frame.physical_both)
    f=frame.loc[valid].reset_index(drop=True);temperature=f.road_temp.to_numpy(float)
    bins=np.searchsorted([-3.,0.,3.],temperature,side='left')
    bins[~np.isfinite(temperature)]=4
    labels=['below_-3','-3_to_0','0_to_3','above_3','missing']
    kinds=['tn','fp','fn','tp']
    categories=(2*f.ice+f.physical_both).to_numpy(int)
    counts=Counter(zip(f.station,f.winter,bins,categories))
    keys=sorted({(s,int(w),int(b)) for s,w,b,_ in counts})
    rows=[]
    for station,winter,number in keys:
        row=dict(station=station,winter=winter,observed_temperature_bin=labels[number])
        row.update({name:counts[(station,winter,number,index)] for index,name in enumerate(kinds)})
        rows.append(row)
    actual=pd.DataFrame(rows);expected=pd.read_csv(study/'baseline_confusion_by_observed_temperature.csv',dtype={'station':str})
    keys=['station','winter','observed_temperature_bin']
    pd.testing.assert_frame_equal(actual[expected.columns].sort_values(keys).reset_index(drop=True),
                                 expected.sort_values(keys).reset_index(drop=True),check_exact=True)
    assert int(actual[kinds].to_numpy().sum())==len(f)
    total={name:int(actual[name].sum()) for name in kinds};positive=int(f.ice.eq(1).sum())
    assert positive==total['tp']+total['fn']
    by_site=f.loc[f.ice.eq(1)].groupby(['station','winter']).size().sort_values(ascending=False)
    top_station,top_winter=by_site.index[0];top_count=int(by_site.iloc[0])
    above_zero=int(((temperature>0)&f.ice.eq(1).to_numpy()).sum())
    days=pd.read_csv(study/'daily_metrics.csv',dtype={'station':str})
    days=days.loc[days.policy.eq('confirm1_hold0_release0')]
    active=int(days.included_f1.sum());false_only=int((days.coverage_accepted&days.false_alarm_only).sum())
    official_style=read(study/'summary.json')['baseline']['all']
    assert active==official_style['active_days'] and false_only==official_style['false_alarm_only_days']
    assert preservation()==frozen
    summary=dict(status='failure_distribution_independently_verified',valid_rows=len(f),
        confusion_groups=len(actual),confusion=total,positive_rows=positive,
        largest_station_winter=dict(station=top_station,winter=int(top_winter),positive_rows=top_count,fraction=top_count/positive),
        positive_rows_observed_temperature_above_zero=above_zero,above_zero_positive_fraction=above_zero/positive,
        active_daily_station_cases=active,false_alarm_only_daily_station_cases=false_only,false_alarm_only_fraction=false_only/active,
        official_competition_score=False,pooled_counts_are_official_score=False,
        labels_changed=False,selection_criteria_changed=False,protected_labels_read=False,
        interpretation='분포와 관측 간 불일치만 진단. 센서 오류·제설·물성 등 원인은 이 자료만으로 확정하지 않음.',
        sources={str(p.relative_to(ROOT)):sha(p) for p in [source,study/'baseline_confusion_by_observed_temperature.csv',study/'daily_metrics.csv',study/'summary.json']},
        audit_code_sha256=sha(Path(__file__)),frozen_counts=list(frozen))
    out.mkdir(parents=True)
    actual.sort_values(keys).to_csv(out/'verified_confusion.csv',index=False)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['sources','interpretation']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
