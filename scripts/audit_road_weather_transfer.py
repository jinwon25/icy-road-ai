"""목표 원문 표본·입력 전량·24추론·대표 3재학습·지표·재표집을 별도로 검산한다."""
from pathlib import Path
import sys
import zipfile

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.evaluate_objective_icing import read,write,verify_preserved

TARGETS=['air_temperature','relative_humidity','wind_speed']
FIELDS=['air_temp','humidity','wind_speed']


def compare(a,b):
    if isinstance(b,dict):
        assert set(a)==set(b)
        return sum(compare(a[k],v) for k,v in b.items())
    if b is None:assert a is None
    elif isinstance(b,(str,bool)):assert a==b
    else:np.testing.assert_allclose(a,b,atol=1e-11,rtol=1e-12)
    return 1


def measure(frame,column):
    y=frame.observed.to_numpy();p=frame[column].to_numpy();d=p-y;n=len(y)
    assert np.isfinite(y).all() and np.isfinite(p).all()
    centered_y=y-y.mean();centered_p=p-p.mean()
    v=np.dot(centered_y,centered_y);s=np.dot(centered_p,centered_p)
    return dict(n=n,mae=float(np.linalg.norm(d,ord=1)/n),rmse=float(np.sqrt(np.dot(d,d)/n)),
        bias=float(d.sum()/n),correlation=float(np.dot(centered_y,centered_p)/np.sqrt(v*s)) if v*s>0 else None,
        r2=float(1-np.dot(d,d)/v) if v>0 else None)


def audit_targets(base,settings):
    inventory=read(base/'source_inventory.json')
    for path,digest in inventory['signatures'].items():assert sha(ROOT/path)==digest,path
    raw=pd.read_parquet(base/'targets.parquet').set_index(['station','time'])
    count=0
    def check(frame):
        nonlocal count
        frame.columns=['station','time']+TARGETS
        frame['station']=frame.station.astype(str).str.strip();frame['time']=pd.to_datetime(frame.time)
        frame=frame.set_index(['station','time'])
        for target in TARGETS:
            value=pd.to_numeric(frame[target],errors='coerce').to_numpy(float)
            lo,hi=settings['quality_ranges'][target]
            value[(~np.isfinite(value))|(value<lo)|(value>hi)|np.isin(value,[-999,-99.9,-99.2,-99.7])]=np.nan
            np.testing.assert_allclose(value,raw.loc[frame.index,target],rtol=0,atol=0,equal_nan=True)
            count+=len(value)
    archive_paths=[ROOT/p for p in inventory['signatures'] if p.endswith('.zip')];assert len(archive_paths)==1
    columns=['관측 지점번호','관측시각 (KST)','기온 (C)','습도 (%)','1분 풍속 (m/s)']
    with zipfile.ZipFile(archive_paths[0]) as archive:
        # 날짜 순서로 고정한 12개 일별 원문. 번호 열을 먼저 읽고 허용 행만 다시 연다.
        for record in inventory['csv_members'][::20]:
            member=record['member']
            with archive.open(member) as stream:
                ids=pd.read_csv(stream,usecols=[columns[0]],dtype=str,encoding='utf-8-sig')
            retained=set(ids.index[ids[columns[0]].str.strip().isin(settings['competition_stations'])]+1)
            with archive.open(member) as stream:
                frame=pd.read_csv(stream,usecols=columns,dtype=str,encoding='utf-8-sig',
                    skiprows=lambda line: line!=0 and line not in retained)
            check(frame.loc[:,columns])
    for i,record in enumerate(inventory['cached_files']):
        path=ROOT/record['path'];assert sha(path)==record['sha256']
        if i%120==0:
            frame=pd.read_parquet(path,columns=['station','time','TA','HM','WS1'])
            assert set(frame.station)<=set(settings['development_stations'])
            if len(frame):check(frame)
    return count


def main():
    out=ROOT/'outputs/private/road_weather_transfer_20261031_v1';target=out/'independent_verification.json'
    if target.exists():raise FileExistsError('Preserve weather verification')
    plan=read(out/'plan.json');settings=plan['settings'];summary=read(out/'summary.json')
    for path,digest in plan['signatures'].items():assert sha(ROOT/path)==digest,path
    for path,digest in summary['files'].items():assert sha(out/path)==digest,path
    frozen=verify_preserved();assert frozen==plan['preservation']
    base=ROOT/settings['input_output'];target_checks=audit_targets(base,settings)
    receipt=read(base/'receipt.json');assert sha(base/'targets.parquet')==receipt['target_sha256']
    f=pd.read_parquet(base/'development.parquet').sort_values(['station','time']).reset_index(drop=True)
    raw=pd.read_parquet(base/'targets.parquet')
    aligned=f[['station','time']].merge(raw,on=['station','time'],how='left',validate='one_to_one')
    for t in TARGETS:np.testing.assert_array_equal(aligned[t],f[t])
    assert not set(f.station)&set(settings['blocked_stations'])
    assert not {'ice','road_temp','state_raw'}&set(f)
    x=pd.read_parquet(out/'features.parquet');reference=pd.DataFrame(index=f.index)
    for column in x:
        if column.startswith('aws_asos_') and column.endswith('_contrast'):
            name=column[len('aws_asos_'):-len('_contrast')];field=FIELDS[TARGETS.index(name)]
            reference[column]=reference['aws_'+field]-reference['asos_'+field]
        elif column=='asos_ground_air_contrast':reference[column]=reference.asos_ground_temp-reference.asos_air_temp
        elif column=='asos_dewpoint_gap':reference[column]=reference.asos_air_temp-reference.asos_dewpoint_obs
        elif column=='aws_dewpoint_gap':reference[column]=reference.aws_air_temp-reference.aws_dewpoint
        elif column.startswith(('asos_','aws_')) and not column.endswith(('_minutes','_km')):
            prefix=column.split('_')[0];age=f[prefix+'_age_minutes']
            reference[column]=f[column].mask((age<=0)|(age>(60 if prefix=='asos' else 15))|age.isna())
        else:reference[column]=f[column]
    pd.testing.assert_frame_equal(reference.astype(float),x,check_exact=True)
    metric_checks=0;replay_values=0;refits=0;bootstrap_values=0;gate_checks=0
    for t,field in zip(TARGETS,FIELDS):
        a=reference['asos_'+field].to_numpy();b=reference['aws_'+field].fillna(reference['asos_'+field]).to_numpy()
        good=f[t].notna().to_numpy()&np.isfinite(a)&np.isfinite(b)
        saved=pd.read_parquet(out/t/'predictions.parquet')
        query=f.loc[f.group.ne('competition')&good]
        pd.testing.assert_frame_equal(query[['station','time','group','winter']].reset_index(drop=True),saved[['station','time','group','winter']],check_exact=True)
        np.testing.assert_array_equal(saved.observed,query[t]);np.testing.assert_array_equal(saved.asos,a[query.index])
        np.testing.assert_array_equal(saved.aws_fallback,b[query.index])
        for record in [r for r in summary['fits'] if r['target']==t]:
            held=record['held'];candidate=record['candidate'];train=f.loc[f.group.ne(held)&good];q=f.loc[f.group.eq(held)&good]
            assert len(train)==record['training_rows'] and len(q)==record['query_rows']
            assert sorted(train.station.unique())==record['training_stations']
            assert sorted(q.station.unique())==record['query_stations']
            assert not set(train.station)&set(q.station)
            stem=candidate+'_'+held;model=joblib.load(out/t/(stem+'.joblib'))
            assert model.get_params()==record['model_parameters'] and list(x)==record['features']
            with deny_network() as attempts,threadpool_limits(limits=2):
                prediction=model.predict(x.loc[q.index])
                if candidate==settings['primary_candidate'] and held=='honam_baekyang':
                    weight=np.ones(len(train))
                    for _,idx in train.reset_index(drop=True).groupby(['station','winter']).groups.items():weight[idx]=1/len(idx)
                    weight/=np.mean(weight)
                    y=train[t].to_numpy()-b[train.index]
                    clone=HistGradientBoostingRegressor(**settings['model']).fit(x.loc[train.index],y,sample_weight=weight)
                    np.testing.assert_array_equal(clone.predict(x.loc[q.index]),prediction);refits+=1
            assert not attempts
            if candidate=='residual_hgb':prediction+=b[q.index]
            if t=='relative_humidity':prediction=np.minimum(np.maximum(prediction,0),100)
            if t=='wind_speed':prediction=np.maximum(prediction,0)
            np.testing.assert_array_equal(prediction,np.load(out/t/(stem+'.npy')))
            np.testing.assert_array_equal(prediction,saved.loc[saved.group.eq(held),candidate])
            replay_values+=len(prediction)
            print('AUDIT',t,candidate,held,flush=True)
        result=summary['reports'][t]
        for c in ['asos','aws_fallback']+settings['candidates']:
            actual=dict(pooled=measure(saved,c),regions={k:measure(q,c) for k,q in saved.groupby('group')},
                        winters={str(k):measure(q,c) for k,q in saved.groupby('winter')})
            metric_checks+=compare(actual,result['metrics'][c])
        for c in settings['candidates']:
            samples=[];weights=[];bs=settings['bootstrap']
            for year in [2024,2025]:
                s=saved.loc[saved.winter.eq(year)].copy();s['day']=s.time.dt.normalize()
                s['delta']=abs(s[c]-s.observed)-abs(s.aws_fallback-s.observed)
                days=pd.date_range(f'{year}-11-01',f'{year+1}-02-28')
                daily=s.groupby('day').agg(total=('delta','sum'),count=('delta','size')).reindex(days,fill_value=0)
                rng=np.random.default_rng(bs['seed']+year-2024)
                starts=rng.integers(0,120,(bs['repetitions'],int(np.ceil(120/bs['block_days']))))
                values=[];counts=[]
                for row in starts:
                    ids=np.concatenate([np.arange(start,start+bs['block_days'])%120 for start in row])[:120]
                    sample=daily.iloc[ids].sum();values.append(sample.total);counts.append(sample['count'])
                samples.append(np.array(values));weights.append(np.array(counts))
            values=sum(samples)/sum(weights);expected=np.load(out/t/(c+'_bootstrap.npy'))
            np.testing.assert_allclose(values,expected,atol=1e-12,rtol=0);bootstrap_values+=len(values)
            expected_stats=result['bootstrap'][c]
            compare(dict(delta_mae=float((abs(saved[c]-saved.observed)-abs(saved.aws_fallback-saved.observed)).mean()),
                quantile025_50_975=np.quantile(values,[.025,.5,.975]).tolist(),fraction_improved=float(np.mean(values<0)),
                repetitions=len(values),interpretation=bs['interpretation']),expected_stats)
            m=result['metrics'][c];bmetrics=result['metrics']['aws_fallback'];g=settings['primary_gates']
            checks=dict(pooled_mae=m['pooled']['mae']/bmetrics['pooled']['mae']<=1-g['minimum_mae_reduction'],
                both_winters=max(m['winters'][y]['mae']/r['mae'] for y,r in bmetrics['winters'].items())<=g['maximum_winter_mae_ratio'],
                every_region=max(m['regions'][r]['mae']/v['mae'] for r,v in bmetrics['regions'].items())<=g['maximum_region_mae_ratio'],
                date_block_upper=np.quantile(values,.975)<g['bootstrap_upper_delta_mae'])
            gate_checks+=compare(checks,result['gates'][c])
        assert result['primary_success']==all(result['gates'][settings['primary_candidate']].values())
    assert summary['successful_primary_targets']==[t for t in TARGETS if summary['reports'][t]['primary_success']]
    assert verify_preserved()==frozen
    result=dict(status='passed',summary_sha256=sha(out/'summary.json'),target_source_sample_values=target_checks,
        matched_target_values=len(f)*3,feature_values=int(x.size),models_replayed=len(summary['fits']),
        replay_values=replay_values,exact_refits=refits,metric_checks=metric_checks,gate_checks=gate_checks,
        bootstrap_values=bootstrap_values,protected_targets_read=False,new_independent_assessment=False,
        audit_source_sha256=sha(Path(__file__)),preservation=frozen)
    write(target,result);print(result,flush=True)


if __name__=='__main__':main()
