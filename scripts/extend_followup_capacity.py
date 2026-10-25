"""미리 정한 600회 선별 규칙만으로 유망 후속 후보를 1200회까지 연장한다."""
import json
from pathlib import Path
import sys
import time
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.two_winter import validate
from src.followup_temperature import feature_table,training_weights
from src.extended_search import temperature_gate
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation


def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')


def main():
    source=ROOT/'outputs/private/followup_temperature_20261024_v1'
    out=ROOT/'outputs/private/followup_capacity_20261024_v1'
    parent=read(source/'plan.json');settings=parent['settings'];summary=read(source/'summary.json')
    assert len(summary['candidates'])==4
    for name,expected in settings['additional_source_sha256'].items():assert sha(ROOT/name)==expected,name
    for name,expected in settings['reference_sha256'].items():assert sha(ROOT/name)==expected,name
    ref600_path=ROOT/settings['fixed_followup']['screen_reference']
    ref1200_path=ROOT/settings['fixed_followup']['final_reference']
    reference600=validate(pd.read_parquet(ref600_path));reference=validate(pd.read_parquet(ref1200_path))
    comparisons={};specs={s['name']:s for s in settings['candidates']}
    for name in specs:
        f=validate(pd.read_parquet(source/name/'predictions.parquet'))
        pd.testing.assert_frame_equal(f[['station','time']],reference600[['station','time']],check_exact=True)
        comparisons[name]=temperature_gate(f,f.prediction,reference600.prediction,settings['temperature_gate'])
    eligible=sorted([n for n,r in comparisons.items() if r['eligible']],key=lambda n:(comparisons[n]['regression']['pooled']['mae'],n))[:2]
    cold='solar_cold_weight_mae600';cold_report=comparisons[cold]
    from src.temperature_transfer import regression_report
    base_report=regression_report(reference600,reference600.prediction)
    cold_ok=(cold_report['regression']['near_freezing']['mae']<=.99*base_report['near_freezing']['mae']
             and cold_report['regression']['pooled']['mae']<=1.03*base_report['pooled']['mae'])
    if cold_ok and cold not in eligible:eligible.append(cold)
    signatures=dict(parent_plan=sha(source/'plan.json'),parent_summary=sha(source/'summary.json'),
        code=sha(Path(__file__)),data=sha(ROOT/settings['data']),reference600=sha(ref600_path),reference1200=sha(ref1200_path),
        new_features=sha(ROOT/'src/followup_temperature.py'))
    extended_specs=[dict(specs[n],name=n.replace('600','1200'),iterations=1200,parent_candidate=n) for n in eligible]
    extended_settings=dict(settings,candidates=extended_specs)
    if out.exists():assert read(out/'plan.json')['signatures']==signatures
    else:
        out.mkdir(parents=True)
        write(out/'plan.json',dict(settings=extended_settings,signatures=signatures,
            screen=dict(reference='v3_same_capacity_600',comparisons=comparisons,selected=eligible,cold_specialist_eligible=bool(cold_ok))))
    frozen=preservation();results={};blend_reports={}
    if eligible:
        data=validate(pd.read_parquet(ROOT/settings['data'])).sort_values(['station','time']).reset_index(drop=True)
        for spec in extended_specs:
            name=spec['name'];initial_name=spec['parent_candidate'];original=source/initial_name
            x=feature_table(data,spec['features']);folder=out/name;folder.mkdir(exist_ok=True);fits=[];parts=[]
            for previous in read(original/'report.json')['fits']:
                group=previous['group'];query=data.loc[data.group.eq(group)]
                train=data.loc[~data.group.eq(group)&data.road_temp.notna()&data.asos_air_temp.notna()]
                assert sorted(train.station.unique())==previous['training_stations'] and len(train)==previous['training_rows']
                assert not set(train.station)&set(query.station)
                record=folder/(group+'.json');modelpath=folder/(group+'.joblib');predpath=folder/(group+'.parquet')
                if record.exists():
                    fit=read(record);assert sha(modelpath)==fit['model_sha256'] and sha(predpath)==fit['prediction_sha256']
                    f=pd.read_parquet(predpath)
                else:
                    assert sha(original/(group+'.joblib'))==previous['model_sha256']
                    model=joblib.load(original/(group+'.joblib'));assert model.n_iter_==600
                    target=train.road_temp.to_numpy(float)
                    if spec.get('residual'):target=target-train.asos_air_temp.to_numpy(float)
                    model.set_params(max_iter=1200,warm_start=True);started=time.perf_counter()
                    with deny_network() as attempts,threadpool_limits(limits=2):
                        model.fit(x.loc[train.index],target,sample_weight=training_weights(train,spec))
                        prediction=model.predict(x.loc[query.index])
                    assert not attempts and model.n_iter_==1200 and np.isfinite(prediction).all()
                    if spec.get('residual'):prediction=prediction+query.asos_air_temp.to_numpy(float)
                    f=query[['station','time','group','winter','ice','road_temp','asos_air_temp']].copy()
                    f['prediction']=np.where(query.asos_air_temp.notna(),prediction,np.nan)
                    f.to_parquet(predpath,index=False,compression='zstd');joblib.dump(model,modelpath,compress=3)
                    fit=dict(candidate=name,group=group,training_rows=len(train),training_stations=sorted(train.station.unique()),
                        features=list(x),parameters=model.get_params(),model_sha256=sha(modelpath),prediction_sha256=sha(predpath),
                        source600_model_sha256=previous['model_sha256'],seconds=time.perf_counter()-started,protected_labels_read=False)
                    write(record,fit);print(name,group,round(fit['seconds'],1),flush=True)
                fits.append(fit);parts.append(f)
            f=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
            pd.testing.assert_frame_equal(f[['station','time']],reference[['station','time']],check_exact=True)
            report=temperature_gate(f,f.prediction,reference.prediction,settings['temperature_gate']);report['fits']=fits
            f.to_parquet(folder/'predictions.parquet',index=False,compression='zstd');write(folder/'report.json',report);results[name]=report
            blend=f.copy();blend.prediction=(blend.prediction+reference.prediction)/2
            blend.to_parquet(out/(name+'_equal_v3.parquet'),index=False,compression='zstd')
            blend_reports[name+'_equal_v3']=temperature_gate(blend,blend.prediction,reference.prediction,settings['temperature_gate'])
            if spec.get('cold_weight'):
                blend.prediction=reference.prediction+.5*np.exp(-(reference.prediction/3)**2)*(f.prediction-reference.prediction)
                blend.to_parquet(out/(name+'_gated_v3.parquet'),index=False,compression='zstd')
                blend_reports[name+'_gated_v3']=temperature_gate(blend,blend.prediction,reference.prediction,settings['temperature_gate'])
            print('RESULT',name,report['regression']['pooled']['mae'],report['gates'],flush=True)
            del x
    assert preservation()==frozen
    write(out/'summary.json',dict(status='fixed_followup_capacity_complete',screen_selected=eligible,
        candidates=results,fixed_blends=blend_reports,reference='v3_1200',protected_labels_read=False,
        new_independent_assessment=False,model_promoted=False,frozen_counts=list(frozen)))
    print('Capacity selection complete',eligible,flush=True)


if __name__=='__main__':main()
