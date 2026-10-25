"""현재 완료된 회귀 후보와 사전 고정 평균을 같은 개발 범위에서 비교한다."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.extended_search import temperature_gate
from src.extended_comparison import physical_ice,block_sensitivity,event_retention
from src.runtime_metrics import runtime_daily
from src.two_winter import validate
from scripts.evaluate_method_blending import preservation

# 탐색 점수로 가중치를 최적화하지 않은 사후 고정 혼합. 독립 선택 검증이라고 주장하지 않는다.
PAIRS={
 'thermal_equal':['thermal_mse600','thermal_mae600'],
 'deep_weather_equal':['hgb_deep_mse600','hgb_deep_mae600'],
 'canonical_weather_equal':['canonical_weather_mse300','canonical_weather_mae300'],
 'canonical_thermal_equal':['canonical_thermal_mse600','canonical_thermal_mae600'],
}


def read(path):return json.loads(path.read_text('utf-8'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--search',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output
    if out.exists():raise FileExistsError('Preserve comparison snapshot')
    freeze=preservation();basepath=ROOT/'outputs/private/two_winter_models_20261024_v1/runtime_predictions.parquet'
    assert sha(basepath)==read(basepath.parent/'audit_runtime.json')['runtime_prediction_sha256']
    frame=validate(pd.read_parquet(basepath));predictions={};sources={};settings=read(ROOT/'config/extended_search_20261024.json')
    pending=[]
    for folder in args.search:
        plan=read(folder/'plan.json')['settings']
        for spec in plan['candidates']:
            file=folder/spec['name']/'predictions.parquet';report=folder/spec['name']/'report.json'
            if not report.exists():pending.append(spec['name']);continue
            f=validate(pd.read_parquet(file));pd.testing.assert_frame_equal(f[['station','time']],frame[['station','time']])
            if spec['name'] in predictions:raise ValueError('Ambiguous candidate name')
            predictions[spec['name']]=f.prediction.to_numpy(float);sources[str(file)]=sha(file)
    for name,names in PAIRS.items():
        if all(n in predictions for n in names):predictions[name]=np.mean([predictions[n] for n in names],axis=0)
    if 'thermal_equal' in predictions:
        predictions['thermal_equal_plus_v2_half']=(predictions['thermal_equal']+frame.temperature_both.to_numpy())/2
        predictions['thermal_equal_plus_v2_quarter']=.75*predictions['thermal_equal']+.25*frame.temperature_both.to_numpy()
    out.mkdir(parents=True);results={};baseline_ice=frame.physical_both.to_numpy(float)
    for name,pred in predictions.items():
        report=temperature_gate(frame,pred,frame.temperature_both,settings['temperature_gate'])
        ice=physical_ice(frame,pred);report['ice']={}
        for year in ['all',2024,2025]:
            part=frame if year=='all' else frame.loc[frame.winter.eq(year)]
            report['ice'][str(year)]=runtime_daily(part,ice[part.index])[0]
        retention,events=event_retention(frame,ice,baseline_ice);events.to_csv(out/(name+'_events.csv'),index=False)
        report['event_retention']=retention
        report['date_sensitivity']=block_sensitivity(frame,pred,frame.temperature_both)
        results[name]=report
        print(name,round(report['regression']['pooled']['mae'],6),retention,flush=True)
    result=dict(status='partial_snapshot' if pending else 'all_requested_searches_complete',created=datetime.now(timezone.utc).isoformat(),
        candidates=results,pending=pending,sources=sources,baseline_sha256=sha(basepath),
        fixed_pairs=PAIRS,protected_labels_read=False,new_independent_assessment=False,
        old_frozen_files=freeze[0],reserved_frozen_files=freeze[1])
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    assert preservation()==freeze

if __name__=='__main__':main()
