"""기존 결빙 탐지와 새 온도 후보의 고정 결합을 비교한다. 임계값 최적화는 하지 않는다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.extended_comparison import physical_ice,event_retention
from src.runtime_metrics import runtime_daily
from src.two_winter import validate
from scripts.evaluate_method_blending import preservation


def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')


def main():
    private=ROOT/'outputs/private';out=private/'extended_ice_combinations_20261024_v1'
    if out.exists():raise FileExistsError('Preserve fixed ice comparison')
    frozen=preservation();base=private/'two_winter_models_20261024_v1/runtime_predictions.parquet'
    assert sha(base)==read(base.parent/'audit_runtime.json')['runtime_prediction_sha256']
    frame=validate(pd.read_parquet(base));sources={str(base.relative_to(ROOT)):sha(base)}
    def load(folder,name):
        path=private/folder/name/'predictions.parquet';f=validate(pd.read_parquet(path))
        pd.testing.assert_frame_equal(f[['station','time']],frame[['station','time']])
        sources[str(path.relative_to(ROOT))]=sha(path);return f.prediction.to_numpy(float)
    thermal=(load('extended_thermal_search_20261024_v1','thermal_mse600')+load('extended_thermal_search_20261024_v1','thermal_mae600'))/2
    cat=load('extended_search_20261024_v1','cat_rmse800')
    ground_path=private/'canonical_thermal_data_20261024_v1/development.parquet'
    ground=validate(pd.read_parquet(ground_path,columns=['station','time','winter','asos_ground_temp']))
    frame=frame.merge(ground.drop(columns='winter'),on=['station','time'],how='left',validate='one_to_one')
    sources[str(ground_path.relative_to(ROOT))]=sha(ground_path)
    old=frame.physical_both.to_numpy(float);preds={'thermal_equal':physical_ice(frame,thermal),'cat_rmse800':physical_ice(frame,cat)}
    assert all(np.array_equal(np.isfinite(old),np.isfinite(p)) for p in preds.values())
    valid=np.isfinite(old);variants={'v2':old};o=old==1
    for name,p in preds.items():
        n=p==1
        variants[name+'_union']=np.where(valid,o|n,np.nan)
        variants[name+'_intersection']=np.where(valid,o&n,np.nan)
        variants[name+'_union_air_cold']=np.where(valid,o|(n&frame.aws_air_temp.le(0).to_numpy()),np.nan)
        variants[name+'_union_ground_cold']=np.where(valid,o|(n&frame.asos_ground_temp.le(0).to_numpy()),np.nan)
    variants['union_thermal_and_cat']=np.where(valid,o|((preds['thermal_equal']==1)&(preds['cat_rmse800']==1)),np.nan)
    variants['union_thermal_and_cat_air_ground']=np.where(valid,o|((preds['thermal_equal']==1)&(preds['cat_rmse800']==1)&frame.aws_air_temp.le(0).to_numpy()&frame.asos_ground_temp.le(0).to_numpy()),np.nan)
    out.mkdir();write(out/'plan.json',dict(candidates=list(variants),sources=sources,code_sha256=sha(Path(__file__)),
        gates=['F1 >= 1.01*baseline','daily precision/recall noninferior','each winter F1 noninferior','each station F1 noninferior','no lost baseline events'],
        selection_scope='fixed post-search development combinations; no independent or nested selection claim'))
    reports={};station_results={}
    for name,p in variants.items():
        reports[name]={}
        for year in ['all',2024,2025]:
            f=frame if year=='all' else frame.loc[frame.winter.eq(year)]
            report,stations,days=runtime_daily(f,p[f.index]);reports[name][str(year)]=report
            if year=='all':station_results[name]=stations;stations.to_csv(out/(name+'_stations.csv'),index=False);days.to_csv(out/(name+'_days.csv'),index=False)
        reports[name]['events'],events=event_retention(frame,p,old);events.to_csv(out/(name+'_events.csv'),index=False)
    baseline=reports['v2'];decisions={}
    for name,r in reports.items():
        if name=='v2':continue
        b=station_results['v2'].set_index('station');s=station_results[name].set_index('station')
        # 지점표의 실제 F1 열을 명시적으로 검사한다.
        column='f1'
        if column not in s:raise ValueError('Unexpected station F1 schema')
        gates=dict(f1=r['all']['f1_fixed_population']>=1.01*baseline['all']['f1_fixed_population'],
            precision=r['all']['precision_available_station_mean']>=baseline['all']['precision_available_station_mean'],
            recall=r['all']['recall_available_station_mean']>=baseline['all']['recall_available_station_mean'],
            each_winter=all(r[str(y)]['f1_fixed_population']>=baseline[str(y)]['f1_fixed_population'] for y in [2024,2025]),
            each_station=bool((s[column].fillna(0)>=b[column].fillna(0)).all()),no_lost_events=r['events']['lost_events']==0)
        decisions[name]=dict(gates=gates,eligible=all(gates.values()))
        print(name,r['all']['f1_fixed_population'],gates,flush=True)
    assert preservation()==frozen
    write(out/'summary.json',dict(status='fixed_ice_combinations_complete',reports=reports,decisions=decisions,
        protected_labels_read=False,new_independent_assessment=False,old_frozen_files=frozen[0],reserved_frozen_files=frozen[1]))

if __name__=='__main__':main()
