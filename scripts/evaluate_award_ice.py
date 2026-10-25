"""일별 F1 목적의 공간 중첩 선택: 기존 점수 재검토와 새 기상 이력 분류기."""
import argparse
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path
import sys
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.award_ice import EXISTING, NEW, THRESHOLDS, SMOOTHING, past_score, threshold_curve, select_row, history_features, station_class_weights
from src.method_blending import domain
from src.qa633_metrics import daily_table, aggregate
from src.ice_methodology import binary_score
from src.submission_runtime import FEATURES
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation

PRIVATE = ROOT/'outputs/private'
SOURCE = PRIVATE/'ice_methodology_20261010_v1'
CONFIG = ROOT/'config/award_ice_experiment_20261024.json'


def read(p):
    return json.loads(p.read_text('utf-8'))


def write(p, data):
    with p.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def metric(frame, prediction):
    pop = sorted(frame.station.unique())
    reports = {}
    for minimum in [144,130,72,1]:
        days = daily_table(frame, prediction, pop, minimum)
        report, stations = aggregate(days,pop)
        report['f1_fixed_population'] = float(stations.f1.fillna(0).mean())
        reports[str(minimum)] = report
    valid = frame.ice.isin([0,1]).to_numpy(); y = frame.ice.to_numpy(float)
    p = np.asarray(prediction)
    counts = {name:int(np.sum(valid & yy & pp)) for name,yy,pp in [
        ('tp',y==1,p==1),('fp',y==0,p==1),('fn',y==1,p==0),('tn',y==0,p==0)]}
    return dict(coverage=reports,**counts)


def candidate_scores(frame):
    for name in (*EXISTING,*NEW):
        for minutes in SMOOTHING:
            yield name, minutes, past_score(frame,frame[name+'_score'],minutes), THRESHOLDS
    yield 'asos_air_temp_le_zero',0,frame.asos_air_temp.le(0).to_numpy(float),np.array([.5])


def search(frame):
    tables=[]
    for name, minutes, score, thresholds in candidate_scores(frame):
        t=threshold_curve(frame,score,thresholds)
        t['candidate']=name;t['smoothing_minutes']=minutes;tables.append(t)
    return pd.concat(tables,ignore_index=True)


def apply_choice(frame,choice):
    if choice['candidate']=='asos_air_temp_le_zero':
        return frame.asos_air_temp.le(0).to_numpy(int)
    score=past_score(frame,frame[choice['candidate']+'_score'],int(choice['smoothing_minutes']))
    return (score>=choice['threshold']).astype(int)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists() or not out.is_relative_to(PRIVATE.resolve()):
        raise ValueError('New private experiment path required')
    plan=read(CONFIG);summary=read(SOURCE/'summary.json');audit=read(SOURCE/'independent_verification.json')
    assert audit['summary_sha256']==sha(SOURCE/'summary.json')
    assert plan['existing_models']==list(EXISTING) and plan['new_models']==list(NEW)
    freeze=preservation();out.mkdir(parents=True)
    write(out/'plan.json',plan|dict(started_at_utc=datetime.now(timezone.utc).isoformat(),
        plan_sha256=sha(CONFIG),thresholds=THRESHOLDS.tolist(),code_sha256=sha(Path(__file__)),
        library_sha256=sha(ROOT/'src/award_ice.py')))
    groups=read(SOURCE/'groups.json');cache={};receipts=[];signatures={}

    def load(name):
        path=SOURCE/name
        assert sha(path)==summary['files'][name],name
        signatures[name]=summary['files'][name]
        return pd.read_parquet(path)

    for key in [*((g,) for g in groups),*combinations(groups,2)]:
        stem='contexts/'+'__'.join(key)
        train=domain(load(stem+'/training_inputs.parquet'))
        q=domain(load(stem+'/query_predictions.parquet')).copy()
        qi=load(stem+'/query_inputs.parquet')
        pd.testing.assert_frame_equal(q[['station','time']].reset_index(drop=True),qi[['station','time']].reset_index(drop=True))
        forbidden=set().union(*(set(groups[g]) for g in key))
        assert not forbidden & set(train.station) and set(q.station)==forbidden
        train=train.reset_index(drop=True);q=q.reset_index(drop=True);qi=qi.reset_index(drop=True)
        tx=history_features(train)
        qx=history_features(qi)
        q['asos_air_temp']=qi.asos_air_temp.to_numpy()
        mask=train.ice.notna();fit=train.loc[mask]
        folder=out/stem;folder.mkdir(parents=True)
        for name in NEW:
            weights=np.ones(len(fit)) if name.endswith('unweighted') else station_class_weights(fit)
            model=HistGradientBoostingClassifier(**plan['new_hgb'])
            started=time.perf_counter()
            with threadpool_limits(limits=2):
                model.fit(tx.loc[mask],fit.ice.to_numpy(int),sample_weight=weights)
                score=binary_score(model,qx)
            joblib.dump(model,folder/(name+'.joblib'),compress=3)
            q[name+'_score']=score
            receipts.append(dict(context=list(key),candidate=name,training_rows=len(fit),
                training_stations=sorted(fit.station.unique()),forbidden_stations=sorted(forbidden),
                features=list(tx),model_sha256=sha(folder/(name+'.joblib')),fit_seconds=time.perf_counter()-started,
                weight_min=float(weights.min()),weight_max=float(weights.max()),weight_mean=float(weights.mean())))
            print('새 분류 학습',key,name,round(receipts[-1]['fit_seconds'],1),flush=True)
        q.to_parquet(folder/'predictions.parquet',index=False,compression='zstd');cache[key]=q
        write(folder/'receipts.json',receipts[-2:])
    write(out/'fit_receipts.json',receipts);write(out/'source_signatures.json',signatures)
    outer_parts=[];decisions={}
    for outer in groups:
        inner=pd.concat([cache[tuple(sorted([outer,held]))].loc[lambda f:f.group.eq(held)] for held in groups if held!=outer],ignore_index=True)
        table=search(inner);table.to_csv(out/(outer+'_selection.csv'),index=False)
        choice=select_row(table)
        existing_choice=select_row(table.loc[~table.candidate.isin(NEW)])
        # 각 모델도 내부 임계값으로만 비교한다. 외부 최고 고정 모델과 선택 절차를 구분한다.
        result=cache[(outer,)].copy()
        for candidate in (*EXISTING,*NEW):
            selected=select_row(table.loc[table.candidate.eq(candidate)])
            result['pred_'+candidate]=apply_choice(result,selected)
        result['pred_selected']=apply_choice(result,choice)
        result['pred_existing_selected']=apply_choice(result,existing_choice)
        result['pred_asos']=result.asos_air_temp.le(0).to_numpy(int)
        result['outer_group']=outer
        decisions[outer]=dict(chosen=choice,existing_only=existing_choice,selection_stations=sorted(inner.station.unique()),
            held_stations=groups[outer],outer_labels_used_for_selection=False)
        outer_parts.append(result)
        print('외부 지역 선택',outer,choice,flush=True)
    write(out/'decisions.json',decisions)
    combined=pd.concat(outer_parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True)
    basepath=PRIVATE/'submission_candidate_20261019_v1/research/baselines/fixed_comparator_predictions.parquet'
    fixed=pd.read_parquet(basepath).sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(combined[['station','time','ice']],fixed[['station','time','ice']])
    combined['pred_current']=fixed.current.to_numpy();combined['pred_always_one']=1;combined['pred_always_zero']=0
    methods=[c for c in combined if c.startswith('pred_')]
    reports={name:metric(combined,combined[name]) for name in methods}
    regional=[];station_parts=[];daily_parts=[]
    for name in methods:
        days=daily_table(combined,combined[name],sorted(combined.station.unique()),144)
        _,stations=aggregate(days,sorted(combined.station.unique()));days['method']=name;stations['method']=name
        daily_parts.append(days);station_parts.append(stations)
        for group,part in combined.groupby('outer_group'):
            r=metric(part,part[name]);regional.append(dict(method=name,group=group,
                f1=r['coverage']['144']['f1_fixed_population'],tp=r['tp'],fp=r['fp'],fn=r['fn']))
    pd.concat(daily_parts).to_csv(out/'daily.csv',index=False)
    pd.concat(station_parts).to_csv(out/'stations.csv',index=False)
    regional=pd.DataFrame(regional);regional.to_csv(out/'regions.csv',index=False)
    combined.to_parquet(out/'outer_predictions.parquet',index=False,compression='zstd')
    selected=regional.loc[regional.method.eq('pred_selected')].set_index('group')
    air=regional.loc[regional.method.eq('pred_asos')].set_index('group')
    wins=int(selected.f1.ge(air.f1-1e-12).sum())
    primary=lambda n:reports[n]['coverage']['144']['f1_fixed_population']
    eligible=primary('pred_selected')>max(primary('pred_current'),primary('pred_asos')) and wins>=3
    # 배포용 최종 선택도 전 개발 OOF 점수에서 수행. 아래 내부 적합값은 성능 보고에 사용하지 않는다.
    fulltable=search(combined);fulltable.to_csv(out/'final_selection.csv',index=False)
    write(out/'final_choice.json',select_row(fulltable))
    assert preservation()==freeze
    result=dict(status='nested_award_ice_complete',reports=reports,region_noninferior_to_air=wins,
        promotion_evidence_met=eligible,new_model_fits=len(receipts),rows=len(combined),
        protected_or_second_winter_outcomes_read=False,new_independent_assessment=False,
        old_frozen_files=freeze[0],reserved_frozen_files=freeze[1],
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    write(out/'summary.json',result)
    print(json.dumps({'primary_f1':{n:primary(n) for n in methods},'eligible':eligible,'region_noninferior':wins},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
