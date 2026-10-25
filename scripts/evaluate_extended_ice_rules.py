"""648개 기상 규칙과 2개 공간 분리 선택 절차를 새 결과로 보존한다."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.extended_search import feature_table
from src.extended_ice_rules import policies,raw_policy,consecutive,DailyAccumulator
from src.runtime_metrics import runtime_daily
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation

def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')

def main():
    private=ROOT/'outputs/private';out=private/'extended_ice_rules_20261024_v1';config=ROOT/'config/extended_ice_rules_20261024.json'
    if out.exists():raise FileExistsError('Preserve completed rule comparison')
    plan=read(config);f=pd.read_parquet(private/'two_winter_models_20261024_v1/runtime_predictions.parquet').sort_values(['station','time']).reset_index(drop=True)
    frozen=preservation();history=feature_table(f,'history');rain=history.aws_rain_15m_past_mean_180m.to_numpy()
    valid=np.isfinite(f[['asos_air_temp','aws_air_temp','aws_humidity','aws_dewpoint']]).all(axis=1).to_numpy()&np.isfinite(rain)&f.asos_age_minutes.between(1,60).to_numpy()&f.aws_age_minutes.between(1,60).to_numpy()
    specs=policies(plan);acc=DailyAccumulator(f,valid);scores=[];counts=[];predictions=[]
    out.mkdir();write(out/'plan.json',dict(settings=plan,config_sha256=sha(config),source_sha256=sha(private/'two_winter_models_20261024_v1/runtime_predictions.parquet'),
        code_sha256=sha(Path(__file__)),library_sha256=sha(ROOT/'src/extended_ice_rules.py'),created_at_utc=datetime.now(timezone.utc).isoformat()))
    for index,spec in enumerate(specs):
        p=consecutive(f,raw_policy(f,rain,spec)&valid,spec['slots']);score,count=acc.compute(p)
        scores.append(score);counts.append(count);predictions.append(np.packbits(p))
        if index%108==0:print('규칙 비교',index,'/',len(specs),flush=True)
    scores=np.stack(scores);groups=sorted(f.group.unique());group_map=f[['station','group']].drop_duplicates().set_index('station').group
    selected={t:np.full(len(f),np.nan) for t in plan['selection_tracks']};decisions={}
    for outer in groups:
        stations=[i for i,s in enumerate(acc.stations) if group_map[s]!=outer]
        inner=scores[:,:,stations].mean(axis=2);decisions[outer]={}
        for track in plan['selection_tracks']:
            objective=inner[:,0] if track=='mean_f1' else inner[:,1:].min(axis=1)
            choice=min(range(len(specs)),key=lambda i:(-objective[i],i))
            positions=f.group.eq(outer).to_numpy();p=np.unpackbits(predictions[choice],count=len(f))
            selected[track][positions]=np.where(valid[positions],p[positions],np.nan)
            decisions[outer][track]=dict(policy_index=choice,spec=specs[choice],selection_f1=float(objective[choice]),
                selection_stations=[acc.stations[i] for i in stations],excluded_stations=sorted(f.loc[positions,'station'].unique()))
    f['common_valid']=valid;reports={};daily=[];station_tables=[]
    comparators={'current':f.physical_both.to_numpy(float),'air_zero':f.asos_air_temp.le(0).to_numpy(float),**selected}
    for name,p in comparators.items():
        f[name]=np.where(valid,p,np.nan);reports[name]={}
        for period in ['all',2024,2025]:
            subset=f if period=='all' else f.loc[f.winter.eq(period)]
            report,st,d=runtime_daily(subset,subset[name]);reports[name][str(period)]=report
            if period=='all':daily.append(d.assign(method=name));station_tables.append(st.assign(method=name))
        # 빠른 탐색 계산과 기존 일별 집계를 대조한다.
        fast,_=acc.compute(np.nan_to_num(f[name],nan=0).astype(bool))
        assert abs(fast[0].mean()-reports[name]['all']['f1_fixed_population'])<1e-12
    table=[]
    for index,spec in enumerate(specs):
        table.append(dict(index=index,**spec,**counts[index],all_f1=float(scores[index,0].mean()),winter2024_f1=float(scores[index,1].mean()),winter2025_f1=float(scores[index,2].mean())))
    pd.DataFrame(table).to_csv(out/'policy_scores.csv',index=False)
    pd.concat(daily).to_csv(out/'daily.csv',index=False);pd.concat(station_tables).to_csv(out/'stations.csv',index=False)
    f.to_parquet(out/'predictions.parquet',index=False,compression='zstd');np.save(out/'station_scores.npy',scores)
    write(out/'decisions.json',decisions)
    assert preservation()==frozen
    write(out/'summary.json',dict(status='extended_ice_rules_complete',policies=len(specs),reports=reports,
        common_valid_rows=int(valid.sum()),all_rows=len(f),protected_labels_read=False,new_independent_assessment=False,
        files={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print({n:{p:v['f1_fixed_population'] for p,v in r.items()} for n,r in reports.items()},flush=True)

if __name__=='__main__':main()
