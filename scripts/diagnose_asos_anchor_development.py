"""기존 개발 점수의 상승을 실제 날짜별 개선과 평가 날짜 분모 변화로 구별한다."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.blind_icing_validation import PRIVATE,DEFAULT,read,write,verify,now
from src.blind_icing import daily_metrics,summarize_days
from src.data_source import sha256_file as sha


def main():
    source=PRIVATE/'asos_parity_development_20261025_v1';out=PRIVATE/'asos_anchor_diagnosis_20261025_v1'
    if out.exists():raise FileExistsError('Preserve diagnosis')
    s=read(source/'summary.json');assert sha(source/'predictions.parquet')==s['predictions_sha256']
    f=pd.read_parquet(source/'predictions.parquet');plan=read(DEFAULT/'plan.json');assert set(f.station).isdisjoint(plan['new_stations'])
    pop=sorted(f.station.unique());base=daily_metrics(f,f.asos_zero,pop,plan['winters']);rows=[]
    for name in plan['candidate_names']:
        d=daily_metrics(f,f[name],pop,plan['winters']);pd.testing.assert_frame_equal(d[['station','date_kst']],base[['station','date_kst']])
        assert np.array_equal(d.valid_slots,base.valid_slots)
        fixed=d.f1.fillna(0).where(base.f1.notna());baseline_calendar=float(fixed.groupby(d.station).mean().reindex(pop).fillna(0).mean())
        changed=f[name].ne(f.asos_zero)&f[name].notna()&f.asos_zero.notna();lost=changed&f.ice.eq(1)&f.asos_zero.eq(1)
        rows.append(dict(candidate=name,reported_f1=s['reports'][name]['all']['f1_fixed_population'],
            fixed_baseline_active_calendar_f1=baseline_calendar,
            baseline_active_days=int(base.f1.notna().sum()),candidate_active_days=int(d.f1.notna().sum()),
            removed_false_alarm_only_days=int((base.f1.notna()&d.f1.isna()&(base.tp+base.fn).eq(0)&base.fp.gt(0)).sum()),
            gained_active_days=int((base.f1.isna()&d.f1.notna()).sum()),
            better_shared_days=int((d.f1>base.f1).sum()),worse_shared_days=int((d.f1<base.f1).sum()),
            suppressed_alarm_rows=int(changed.sum()),suppressed_positive_rows=int(lost.sum()),
            suppressed_positive_air_min=float(f.loc[lost,'asos_air_temp'].min()) if lost.any() else None,
            suppressed_positive_air_max=float(f.loc[lost,'asos_air_temp'].max()) if lost.any() else None))
    out.mkdir(parents=True);pd.DataFrame(rows).to_csv(out/'decomposition.csv',index=False)
    write(out/'summary.json',dict(status='old_development_calendar_decomposition_complete',at_utc=now(),rows=rows,
        new_outcomes_read=False,metric_is_diagnostic_not_replacement=True,source_sha256=sha(source/'predictions.parquet'),code_sha256=sha(Path(__file__))))
    verify(DEFAULT);print(pd.DataFrame(rows).to_string(index=False),flush=True)


if __name__=='__main__':main()
