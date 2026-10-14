"""행별 규칙·NumPy 날짜 집계·내부 선택을 별도 계산으로 검산한다."""
from datetime import datetime,timezone
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import read,write,preservation
from scripts.audit_qa633_development import reference
from scripts.audit_temperature_blind_validation import compare
from scripts.review_weather_memory_events import reconstruct
from src.event_retention import compare_event_retention

OUT=ROOT/'outputs/private/thermal_consensus_20261013_v1'
SOURCE=ROOT/'outputs/private/weather_memory_controls_20261013_v1'


def independent_rule(f,spec):
    a=f.nohistory12_mse300.to_numpy(float);b=f.nohistory12_mae300.to_numpy(float)
    mode=spec['aggregation'];t=(a+b)/2 if mode=='mean' else np.fmin(a,b) if mode=='coldest' else np.fmax(a,b)
    # 한쪽 온도가 결측이면 다른 성분으로 임의 대체하지 않는다.
    t[np.isnan(a)|np.isnan(b)]=np.nan
    w=f[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].to_numpy(float)
    cold=np.less_equal(t,spec['cold_threshold']);dew=np.greater_equal(w[:,0]-t,spec['dewpoint_margin'])
    p=(cold&(dew|np.greater(w[:,1],0)|np.greater(w[:,2],0))).astype(int)
    missing=~np.isfinite(t)|np.isnan(w).all(axis=1);p[missing]=f.original.to_numpy(int)[missing]
    return p,int(missing.sum())


def main():
    target=OUT/'independent_verification.json'
    if target.exists():raise FileExistsError('Preserve policy audit')
    s=read(OUT/'summary.json');policies=read(OUT/'policies.json');groups=read(OUT/'groups.json');decisions=read(OUT/'decisions.json')
    for rel,h in read(OUT/'input_signatures.json').items():assert sha(ROOT/rel)==h
    for rel,h in s['files'].items():assert sha(OUT/rel)==h
    f=pd.read_parquet(OUT/'predictions.parquet');pop=sorted(f.station.unique());checked=0;fallback={}
    day_csv=pd.read_csv(OUT/'daily_metrics.csv',dtype={'station':str},parse_dates=['date_kst'])
    st_csv=pd.read_csv(OUT/'station_metrics.csv',dtype={'station':str})
    for name,spec in policies.items():
        p,n=independent_rule(f,spec);np.testing.assert_array_equal(p,f[name]);checked+=len(f);fallback[name]=n
    baseline_events=reconstruct(f,'original_trio')
    for name,item in s['reports'].items():
        for n in [144,130,72,1]:
            r,st,days=reference(f,name,pop,n);compare(r,item['report']['daily'][str(n)])
            d=day_csv.loc[day_csv.policy.eq(name)&day_csv.minimum_valid_slots.eq(n)].reset_index(drop=True)
            t=st_csv.loc[st_csv.policy.eq(name)&st_csv.minimum_valid_slots.eq(n)].reset_index(drop=True)
            pd.testing.assert_frame_equal(d[days.columns],days,check_exact=False,atol=1e-12,rtol=0)
            pd.testing.assert_frame_equal(t[st.columns],st,check_exact=False,atol=1e-12,rtol=0)
        y=f.ice.to_numpy(float);p=f[name].to_numpy(int);v=np.isfinite(y)
        for key,mask in [('tp',(y==1)&(p==1)),('fp',(y==0)&(p==1)),('fn',(y==1)&(p==0)),('tn',(y==0)&(p==0))]:assert item['report'][key]==int((v&mask).sum())
        ev=reconstruct(f,name);stored=pd.read_csv(OUT/(name+'_events.csv'),dtype={'station':str})
        pd.testing.assert_frame_equal(ev,stored);assert compare_event_retention(baseline_events,ev)==item['retention']
    # 실제 감사된 온도 모델의 이중 공간 제외 이력을 확인한다.
    fit=read(SOURCE/'fit_receipts.json')
    inner_checked=0
    for g,decision in decisions.items():
        assert g not in decision['selection_groups'] and not decision['outer_labels_used']
        path=SOURCE/g/'inner_oof.parquet';inner=pd.read_parquet(path)
        assert not set(inner.station)&set(groups[g])
        for h in decision['selection_groups']:
            for candidate in ['nohistory12_mse300','nohistory12_mae300']:
                receipt=next(r for r in fit if r['candidate']==candidate and set(r['excluded_groups'])=={g,h})
                assert not set(receipt['training_stations'])&(set(groups[g])|set(groups[h]))
        data=inner.merge(f[['station','time','ice','original','aws_dewpoint','rain15_max_3h','asos_snow_cm']],on=['station','time'],validate='one_to_one')
        t=data.equal_distance_mse_mae300.to_numpy();w=data[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].to_numpy()
        base=((t<=0)&((w[:,0]>=t)|(w[:,1]>0)|(w[:,2]>0))).astype(int);missing=~np.isfinite(t)|np.isnan(w).all(axis=1);base[missing]=data.original.to_numpy()[missing]
        data['original_trio']=base;be=reconstruct(data,'original_trio');br={n:reference(data,'original_trio',sorted(data.station.unique()),int(n))[0] for n in ['144','1']}
        eligible=[]
        for name,spec in policies.items():
            p,_=independent_rule(data,spec);data[name]=p
            metrics={n:reference(data,name,sorted(data.station.unique()),int(n))[0] for n in ['144','1']}
            item=decision['candidates'][name]
            for n in metrics:compare(metrics[n],item['report']['daily'][n])
            daily=all(metrics[n][m+'_available_station_mean']+1e-12>=br[n][m+'_available_station_mean'] for n in metrics for m in ['precision','recall','f1'])
            y=data.ice.to_numpy(float);v=np.isfinite(y);fp=int((v&(y==0)&(p==1)).sum());fn=int((v&(y==1)&(p==0)).sum())
            station=all(int(((d.ice==1)&(d[name]==1)).sum())>=int(((d.ice==1)&(d.original_trio==1)).sum()) for _,d in data.groupby('station'))
            ret=compare_event_retention(be,reconstruct(data,name));assert ret==item['retention']
            ok=daily and station and fp<=decision['baseline_report']['fp'] and fn<=decision['baseline_report']['fn'] and ret['lost_events']==0
            assert ok==item['eligible']
            if ok:eligible.append(name)
            inner_checked+=len(data)
        assert eligible==decision['accepted']
        chosen=min(eligible,key=lambda n:(-decision['candidates'][n]['report']['daily']['144']['f1_available_station_mean'],decision['candidates'][n]['report']['fp'],n)) if eligible else 'original_trio'
        assert chosen==decision['chosen']
        outer=f.loc[f.outer_group.eq(g)];np.testing.assert_array_equal(outer.nested_selected,outer[chosen])
    freezes=preservation();write(target,dict(status='independent_thermal_consensus_audit_passed',audited_at_utc=datetime.now(timezone.utc).isoformat(),
        summary_sha256=sha(OUT/'summary.json'),audit_source_sha256=sha(Path(__file__)),rule_values_verified=checked,inner_rule_values_verified=inner_checked,
        daily_rows_verified=len(day_csv),station_rows_verified=len(st_csv),fallback_rows=fallback,
        double_group_fit_contexts_checked=24,assessment_outcomes_used=False,new_model_fits=0,old_frozen_files=freezes[0],reserved_frozen_files=freezes[1]))
    print(read(target))


if __name__=='__main__':main()
