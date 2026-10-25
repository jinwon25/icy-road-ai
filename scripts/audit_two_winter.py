"""두 겨울 모델의 학습 제외·온도 오차·고정 물리 판정·채택 기준을 검증한다."""
import argparse
import json
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.two_winter import validate,daily
from src.submission_runtime import FEATURES
from src.data_source import sha256_file as sha
from scripts.audit_award_ice import reference_features,reference_f1
from scripts.evaluate_method_blending import preservation


def read(p):return json.loads(p.read_text('utf-8'))


def errors(frame,column):
    good=np.isfinite(frame.road_temp)&np.isfinite(frame[column]);f=frame.loc[good]
    e=f[column].to_numpy()-f.road_temp.to_numpy()
    return dict(n=len(e),mae=float(np.abs(e).mean()),rmse=float(np.sqrt(np.mean(e**2))),bias=float(e.mean()))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',required=True,type=Path)
    args=parser.parse_args();out=args.experiment;dest=out/'audit.json'
    if dest.exists():raise FileExistsError('Preserve completed audit')
    summary=read(out/'summary.json');plan=read(out/'plan.json');freeze=preservation()
    for name,digest in summary['files'].items():assert sha(out/name)==digest,name
    assert sha(ROOT/'src/two_winter.py')==plan['library_sha256']
    assert sha(ROOT/'scripts/evaluate_two_winter.py')==plan['code_sha256']
    source=ROOT/'outputs/private/two_winter_development_20261024_v1'
    data=validate(pd.read_parquet(source/'development.parquet')).sort_values(['station','time']).reset_index(drop=True)
    assert sha(source/'development.parquet')==plan['data_sha256']
    frame=validate(pd.read_parquet(out/'outer_predictions.parquet'))
    checked=0
    for r in read(out/'fits.json'):
        query=data.loc[data.group.isin(r['context'])]
        assert not set(query.station)&set(r['training_stations'])
        path=out/r['model_path'];assert sha(path)==r['model_sha256']
        if len(r['context'])!=1:continue
        q=pd.read_parquet(out/'contexts'/r['context'][0]/'predictions.parquet')
        pd.testing.assert_frame_equal(q[['station','time']].reset_index(drop=True),query[['station','time']].reset_index(drop=True))
        model=joblib.load(path)
        if r['kind']=='temperature':
            with threadpool_limits(limits=2):p=model.predict(query[list(FEATURES)])
            # 두 성분 평균을 별도 배열에 누적 후 저장 예측과 대조한다.
            key=(r['context'][0],r['scope'])
            replay.setdefault(key,[]).append(p)
            if len(replay[key])==2:
                expected=np.where(query.asos_air_temp.notna(),np.mean(replay[key],axis=0),np.nan)
                np.testing.assert_allclose(expected,q['temperature_'+r['scope']],atol=1e-12,rtol=0,equal_nan=True)
        else:
            pieces=[]
            for _,part in query.groupby('winter'):
                features=reference_features(part);features.index=part.index;pieces.append(features)
            x=pd.concat(pieces).sort_index()
            with threadpool_limits(limits=2):p=model.predict_proba(x)[:,list(model.classes_).index(1)]
            np.testing.assert_allclose(p,q['score_'+r['name']],atol=1e-12,rtol=0)
        checked+=len(query)
    comparisons={}
    for period in ['all',2024,2025]:
        f=frame if period=='all' else frame.loc[frame.winter.eq(period)]
        comparisons[str(period)]={s:errors(f,'temperature_'+s) for s in ['first','both']}
        for scope in ['first','both']:
            expected=summary['regression'][str(period)][scope]['pooled']
            for key in ['mae','rmse','bias']:assert abs(expected[key]-comparisons[str(period)][scope][key])<1e-12
    regional=[]
    for (group,winter),f in frame.groupby(['group','winter']):
        regional.append(dict(group=group,winter=int(winter),first_mae=errors(f,'temperature_first')['mae'],both_mae=errors(f,'temperature_both')['mae']))
    regional=pd.DataFrame(regional);regional.to_csv(out/'temperature_regions.csv',index=False)
    cold=frame.loc[frame.road_temp.between(-2,2)]
    cold_metrics={s:errors(cold,'temperature_'+s) for s in ['first','both']}
    wins=sum(errors(f,'temperature_both')['mae']<=errors(f,'temperature_first')['mae'] for _,f in frame.groupby('group'))
    old=summary['regression']['all']['first'];new=summary['regression']['all']['both']
    gates=dict(pooled_improves=new['pooled']['mae']<old['pooled']['mae'],station_mean_improves=new['station_macro']['mae']<old['station_macro']['mae'],
        neither_winter_over_5pct_worse=all(comparisons[str(y)]['both']['mae']<=1.05*comparisons[str(y)]['first']['mae'] for y in [2024,2025]),
        at_least_three_regions_noninferior=wins>=3,cold_mae_within_5pct=cold_metrics['both']['mae']<=1.05*cold_metrics['first']['mae'])
    # 온도 변경이 기존 고정 결빙 조건에 미치는 영향도 같은 공간 제외 예측에서 확인한다.
    private=ROOT/'outputs/private';release=private/'releases/20261007/outputs/private'
    watercols=['rain15_max_3h','asos_snow_cm']
    first=pd.read_parquet(private/'submission_candidate_20261019_v1/data/research_weather_inputs.parquet',columns=['station','time',*watercols])
    water=[first]
    for station in sorted(frame.station.unique()):
        water.append(pd.read_parquet(release/'external_reserved_predictions_v1'/('inputs_'+station+'.parquet'),columns=['station','time',*watercols]))
    frame=frame.merge(pd.concat(water,ignore_index=True),on=['station','time'],validate='one_to_one')
    physical={}
    for scope in ['first','both']:
        temp=frame['temperature_'+scope];wet=frame.aws_dewpoint.ge(temp)|frame.rain15_max_3h.gt(0)|frame.asos_snow_cm.gt(0)
        frame['physical_'+scope]=(temp.le(0)&wet).astype(int)
        physical[scope]={}
        for period in ['all',2024,2025]:
            f=frame if period=='all' else frame.loc[frame.winter.eq(period)]
            r,_,_=daily(f,f['physical_'+scope]);physical[scope][str(period)]=r
    frame.to_parquet(out/'audited_predictions.parquet',index=False,compression='zstd')
    assert preservation()==freeze
    audit=dict(status='two_winter_audit_passed',summary_sha256=sha(out/'summary.json'),replayed_model_predictions=checked,
        temperature=comparisons,cold_temperature=cold_metrics,region_wins=int(wins),temperature_gates=gates,
        temperature_adopt=all(gates.values()),physical=physical,
        previous_temporal_holdout_reclassified=True,new_independent_assessment=False,protected_labels_read=False,
        old_frozen_files=freeze[0],reserved_frozen_files=freeze[1])
    dest.write_text(json.dumps(audit,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    print(json.dumps(audit,ensure_ascii=False),flush=True)

replay={}
if __name__=='__main__':main()
