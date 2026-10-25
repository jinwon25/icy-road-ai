"""저장 분류기·지역 이중 제외·임계값 선택을 독립 날짜별 계산으로 감사한다."""
import argparse
from itertools import combinations
import json
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.two_winter import validate,THRESHOLDS
from src.thermal_extended import feature_table as thermal
from src.solar_memory_search import feature_table as solar
from src.terrain_thermal import feature_table as terrain
from src.offline_runtime import deny_network
from scripts.evaluate_method_blending import preservation


def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')


def independently_count(frame,scores,thresholds):
    """확률 구간 히스토그램 대신 날짜별 정렬과 검색으로 TP/FP/FN을 계산한다."""
    pop=sorted(frame.station.unique());f=frame[['station','time','ice']].copy()
    f['score']=np.asarray(scores);f=f.loc[f.ice.isin([0,1])];f['day']=pd.to_datetime(f.time).dt.normalize()
    totals={k:np.zeros(len(thresholds)) for k in ['tp','fp','fn']}
    sums={s:np.zeros(len(thresholds)) for s in pop};counts={s:np.zeros(len(thresholds)) for s in pop}
    for (station,_),day in f.groupby(['station','day'],sort=False):
        pos=np.sort(day.loc[day.ice.eq(1),'score'].to_numpy());neg=np.sort(day.loc[day.ice.eq(0),'score'].to_numpy())
        tp=len(pos)-np.searchsorted(pos,thresholds,side='left');fp=len(neg)-np.searchsorted(neg,thresholds,side='left');fn=len(pos)-tp
        for key,value in [('tp',tp),('fp',fp),('fn',fn)]:totals[key]+=value
        denominator=2*tp+fp+fn;valid=(len(day)>=144)&(denominator>0)
        sums[station]+=np.divide(2*tp,denominator,out=np.zeros(len(thresholds)),where=valid);counts[station]+=valid
    means=[np.divide(sums[s],counts[s],out=np.zeros(len(thresholds)),where=counts[s]>0) for s in pop]
    return pd.DataFrame(dict(threshold=thresholds,f1_fixed_population=np.mean(means,axis=0),**totals))


def pick(table,track):
    return table.sort_values([track,'fp','threshold','candidate'],ascending=[False,True,False,True],kind='stable').iloc[0].to_dict()


def main():
    p=argparse.ArgumentParser();p.add_argument('--search',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    frozen=preservation();plan=read(a.search/'plan.json');settings=plan['settings'];summary=read(a.search/'summary.json')
    assert summary['fits']==len(settings['candidates'])*10
    for name,expected in plan['signatures'].items():assert sha(ROOT/name)==expected,name
    for name,expected in summary['files'].items():assert sha(a.search/name)==expected,name
    if a.output.exists():raise FileExistsError('Preserve completed audit')
    data=validate(pd.read_parquet(ROOT/settings['data'])).sort_values(['station','time']).reset_index(drop=True)
    availability=data.asos_air_temp.notna()&data.asos_age_minutes.gt(0)&data.asos_age_minutes.le(60)&data[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].notna().any(axis=1)
    groups=sorted(set(data.group)-{'competition'});contexts=[*((g,) for g in groups),*combinations(groups,2)]
    predictions={};checks=[];cache={}
    with deny_network() as attempts,threadpool_limits(limits=2):
        for spec in settings['candidates']:
            name=spec['name'];kind=spec['features'];folder=a.search/name;predictions[name]={}
            if kind not in cache:cache[kind]=(thermal if kind=='thermal' else terrain if kind=='history_terrain' else solar)(data,kind)
            x=cache[kind]
            for context in contexts:
                stem='__'.join(context);receipt=read(folder/(stem+'.json'));stored=pd.read_parquet(folder/(stem+'.parquet'))
                train=data.loc[~data.group.isin(context)&data.ice.isin([0,1])&availability];query=data.loc[data.group.isin(context)]
                assert list(context)==receipt['excluded_groups'] and len(train)==receipt['training_rows']
                assert sorted(train.station.unique())==receipt['training_stations'] and not set(train.station)&set(query.station)
                assert receipt['positive_weight']==spec['positive_weight'] and list(x)==receipt['features']
                model=joblib.load(folder/(stem+'.joblib'))
                assert all(model.get_params()[k]==v for k,v in settings['parameters'].items())
                pd.testing.assert_frame_equal(query[['station','time','winter','group','ice','asos_air_temp']].reset_index(drop=True),stored[['station','time','winter','group','ice','asos_air_temp']].reset_index(drop=True))
                np.testing.assert_array_equal(stored.available,availability.loc[query.index])
                score=model.predict_proba(x.loc[query.index])[:,list(model.classes_).index(1)]
                np.testing.assert_allclose(score,stored.score,rtol=0,atol=1e-12)
                predictions[name][context]=stored
                checks.append(dict(candidate=name,excluded_groups=list(context),rows=len(query),model_sha256=sha(folder/(stem+'.joblib'))))
            print('분류 모델 재실행 검산',name,len(contexts),flush=True)
    assert not attempts
    names=[s['name'] for s in settings['candidates']];decisions=read(a.search/'decisions.json');output=pd.read_parquet(a.search/'predictions.parquet');curve_checks=0;decision_checks=0
    for outer in groups:
        tables=[]
        for name in [*names,'asos_zero']:
            stored=predictions[names[0] if name=='asos_zero' else name]
            inner=pd.concat([stored[tuple(sorted([outer,h]))].loc[lambda f:f.group.eq(h)] for h in groups if h!=outer],ignore_index=True)
            inner.loc[~inner.available,'ice']=np.nan
            scores=inner.asos_air_temp.le(0).to_numpy(float) if name=='asos_zero' else inner.score.to_numpy()
            thresholds=np.array([.5]) if name=='asos_zero' else THRESHOLDS
            table=independently_count(inner,scores,thresholds);table['mean_f1']=table.f1_fixed_population
            winters=[]
            for year in [2024,2025]:
                mask=inner.winter.eq(year).to_numpy();winters.append(independently_count(inner.loc[mask],scores[mask],thresholds).f1_fixed_population.to_numpy())
            table['worst_winter_f1']=np.minimum(*winters);table['candidate']=name;tables.append(table)
        table=pd.concat(tables,ignore_index=True);saved=pd.read_csv(a.search/(outer+'_selection.csv'),float_precision='round_trip')
        assert set(table)==set(saved)
        pd.testing.assert_frame_equal(table[saved.columns],saved,check_dtype=False,check_exact=False,rtol=0,atol=1e-12);curve_checks+=len(table)
        query=output.loc[output.group.eq(outer)].reset_index(drop=True)
        for track in settings['selection_tracks']:
            for name in [*names,'selected']:
                choice=pick(table if name=='selected' else table.loc[table.candidate.eq(name)],track)
                if name=='selected':
                    expected=decisions[outer][track]
                    assert choice['candidate']==expected['candidate'] and choice['threshold']==expected['threshold'];decision_checks+=1
                source=predictions[names[0] if choice['candidate']=='asos_zero' else choice['candidate']][(outer,)]
                pd.testing.assert_frame_equal(source[['station','time']].reset_index(drop=True),query[['station','time']])
                score=source.asos_air_temp.le(0).to_numpy(float) if choice['candidate']=='asos_zero' else source.score.to_numpy()
                actual=np.where(query.available,score>=choice['threshold'],np.nan)
                np.testing.assert_array_equal(actual,query[name+'_'+track])
        print('임계값 독립 검산',outer,len(table),flush=True)
    report_checks=0
    for name,reports in summary['reports'].items():
        for year in ['all',2024,2025]:
            f=output.copy() if year=='all' else output.loc[output.winter.eq(year)].copy();f.loc[~f.available,'ice']=np.nan
            # 결측을 이미 정답 분모에서 제외했으므로 임계값 계산의 대체값은 점수에 영향을 주지 않는다.
            value=independently_count(f,f[name].fillna(0).to_numpy(float),np.array([.5])).f1_fixed_population.iloc[0]
            assert abs(value-reports[str(year)]['f1_fixed_population'])<1e-12;report_checks+=1
    assert preservation()==frozen
    a.output.mkdir(parents=True);write(a.output/'receipt.json',dict(status='classification_models_nested_selection_and_daily_f1_verified',model_checks=checks,
        selection_curve_rows=curve_checks,selected_decisions=decision_checks,report_f1_checks=report_checks,protected_labels_read=False,
        old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],search_summary_sha256=sha(a.search/'summary.json'),audit_code_sha256=sha(Path(__file__))))
    print('분류 감사 완료',len(checks),curve_checks,report_checks,flush=True)


if __name__=='__main__':main()
