"""Python 튜플별 정답 계수로 입력 중복 집계를 별도 검산한다."""
from collections import defaultdict
from pathlib import Path
import sys
import math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.blind_icing_validation import DEFAULT,verify,read,write,now,old_freezes
from scripts.audit_residual_and_trend import FEATURES


def main():
    out=ROOT/'outputs/private/weather_information_20261025_v1';plan=read(out/'plan.json');summary=read(out/'summary.json')
    if (out/'audit.json').exists():raise FileExistsError('Preserve completed audit')
    source=DEFAULT/'training.parquet';assert sha(source)==plan['source_sha256']
    f=pd.read_parquet(source);assert set(f.station).isdisjoint(read(ROOT/'config/residual_icing_20261025.json')['blocked_stations'])
    f=f.loc[f.available&f.ice.isin([0,1])].reset_index(drop=True);checks=0
    for result in summary['results']:
        q=f if result['scope']=='all_23' else f.loc[~f.group.eq('competition')]
        x=q[FEATURES].copy();x['dewpoint_depression']=q.asos_air_temp-q.asos_dewpoint_obs;x['ground_dewpoint_gap']=q.asos_ground_temp-q.asos_dewpoint_obs
        if 'station' in result['view']:x['station']=q.station
        if 'age' in result['view']:x['age']=q.asos_age_minutes
        counts=defaultdict(lambda:[0,0])
        for row,label in zip(x.itertuples(index=False,name=None),q.ice):
            key=tuple(None if isinstance(v,float) and math.isnan(v) else v for v in row);counts[key][int(label)]+=1
        groups=list(counts.values());total=sum(p for n,p in groups);mixed=[(n,p) for n,p in groups if n and p]
        expected=dict(rows=len(q),positive_rows=total,unique_inputs=len(groups),mixed_input_groups=len(mixed),mixed_rows=sum(n+p for n,p in mixed),
            positive_rows_in_mixed_groups=sum(p for n,p in mixed),minimum_observed_errors=sum(min(n,p) for n,p in groups),minimum_fp_if_all_observed_positives_retained=sum(n for n,p in groups if p))
        for key,value in expected.items():assert result[key]==value,(result['view'],key);checks+=1
        ordered=sorted(groups,key=lambda row:row[1]/sum(row),reverse=True);tp=fp=0;best=0.
        for n,p in ordered:
            tp+=p;fp+=n
            if total+tp+fp:best=max(best,2*tp/(total+tp+fp))
        assert abs(result['label_aware_pooled_f1_upper_bound']-best)<1e-12;checks+=1
        print('CHECKED',result['scope'],result['view'],flush=True)
    verify(DEFAULT);assert old_freezes()==(47,549)
    write(out/'audit.json',dict(status='passed',at_utc=now(),summary_sha256=sha(out/'summary.json'),code_sha256=sha(Path(__file__)),independent_tuple_count_checks=checks,new_four_site_outcomes_used=False))


if __name__=='__main__':main()
