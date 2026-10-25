"""선택된 공간 예측을 독립 날짜 집계·모델 재실행·날짜 블록 재표집으로 감사한다."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.method_blending import domain
from src.submission_runtime import FEATURES
from src.ice_event_metrics import event_metrics
from scripts.evaluate_method_blending import preservation


def read(path):return json.loads(path.read_text('utf-8'))


def reference_features(frame):
    """정규 10분 격자에 재색인한 뒤 한 칸 이동한 정수 창. 시간창 구현과 별도 계산."""
    f=frame.reset_index(drop=True);x=f[list(FEATURES)].astype(float).copy()
    x['air_dewpoint_gap']=x.aws_air_temp-x.aws_dewpoint
    for hours in [6,24]:
        for column,operation in [('aws_air_temp','mean'),('aws_air_temp','min'),('aws_humidity','mean'),('aws_rain_15m','max')]:
            name=f'{column}_past_{hours}h_{operation}';x[name]=np.nan
            for _,part in f.groupby('station'):
                part=part.sort_values('time');grid=pd.date_range(part.time.min(),part.time.max(),freq='10min')
                series=pd.Series(part[column].to_numpy(float),index=pd.DatetimeIndex(part.time)).reindex(grid)
                result=getattr(series.shift().rolling(hours*6,min_periods=int(np.ceil(.8*hours*6))),operation)()
                x.loc[part.index,name]=result.reindex(part.time).to_numpy()
    return x


def reference_smoothing(frame,score,minutes):
    if not minutes:return np.asarray(score,float)
    f=frame[['station','time']].reset_index(drop=True).copy();f['score']=np.asarray(score,float);out=f.score.copy()
    for _,part in f.groupby('station'):
        part=part.sort_values('time');grid=pd.date_range(part.time.min(),part.time.max(),freq='10min')
        s=pd.Series(part.score.to_numpy(),index=pd.DatetimeIndex(part.time)).reindex(grid)
        prior=s.shift().rolling(minutes//10,min_periods=int(np.ceil(.8*minutes/10))).mean()
        estimate=.5*(s+prior)
        out.loc[part.index]=estimate.fillna(s).reindex(part.time).to_numpy()
    return out.to_numpy()


def reference_f1(frame,prediction,minimum=144):
    f=frame[['station','time','ice']].copy();f['p']=np.asarray(prediction,int)
    f=f.loc[f.ice.isin([0,1])];f['date']=f.time.dt.normalize()
    f['tp']=((f.ice==1)&(f.p==1)).astype(int);f['fp']=((f.ice==0)&(f.p==1)).astype(int)
    f['fn']=((f.ice==1)&(f.p==0)).astype(int)
    d=f.groupby(['station','date']).agg(n=('ice','size'),tp=('tp','sum'),fp=('fp','sum'),fn=('fn','sum'))
    den=2*d.tp+d.fp+d.fn;d['f1']=(2*d.tp/den.where(den>0)).where(d.n>=minimum)
    stations=d.groupby('station').f1.mean().reindex(sorted(frame.station.unique())).fillna(0)
    return float(stations.mean())


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',required=True,type=Path)
    args=parser.parse_args();out=args.experiment;target=out/'independent_audit.json'
    if target.exists():raise FileExistsError('Preserve completed audit')
    summary=read(out/'summary.json');decisions=read(out/'decisions.json');freeze=preservation()
    for name,digest in summary['files'].items():assert sha(out/name)==digest,name
    plan=read(out/'plan.json')
    assert sha(ROOT/'src/award_ice.py')==plan['library_sha256']
    assert sha(ROOT/'scripts/evaluate_award_ice.py')==plan['code_sha256']
    source=ROOT/'outputs/private/ice_methodology_20261010_v1'
    source_summary=read(source/'summary.json')
    for name,digest in read(out/'source_signatures.json').items():
        assert sha(source/name)==digest==source_summary['files'][name]
    score_rows=0;selected_rows=0
    for outer,decision in decisions.items():
        assert not set(decision['selection_stations'])&set(decision['held_stations'])
        table=pd.read_csv(out/(outer+'_selection.csv'),float_precision='round_trip')
        expected=min(table.to_dict('records'),key=lambda r:(-r['f1_fixed_population'],r['fp'],-r['threshold'],r['candidate'],r['smoothing_minutes']))
        assert expected['candidate']==decision['chosen']['candidate'] and expected['threshold']==decision['chosen']['threshold']
        stem='contexts/'+outer
        qi=pd.read_parquet(source/stem/'query_inputs.parquet');q=domain(pd.read_parquet(out/stem/'predictions.parquet'))
        x=reference_features(qi)
        for receipt in read(out/stem/'receipts.json'):
            assert not set(receipt['training_stations'])&set(receipt['forbidden_stations'])
            assert set(receipt['forbidden_stations'])==set(q.station)
            path=out/stem/(receipt['candidate']+'.joblib');assert sha(path)==receipt['model_sha256']
            model=joblib.load(path)
            with threadpool_limits(limits=2):score=model.predict_proba(x)[:,list(model.classes_).index(1)]
            np.testing.assert_allclose(score,q[receipt['candidate']+'_score'],rtol=0,atol=1e-12);score_rows+=len(q)
        inner_parts=[]
        for held in decisions:
            if held==outer:continue
            part=pd.read_parquet(out/'contexts'/'__'.join(sorted([outer,held]))/'predictions.parquet')
            inner_parts.append(part.loc[part.group.eq(held)])
        inner=pd.concat(inner_parts,ignore_index=True)
        # 선택 후보와 상위 경쟁 후보의 점수를 기존 집계 모듈 없이 검산한다.
        rows=table.sort_values('f1_fixed_population',ascending=False).head(3).to_dict('records')+[decision['chosen']]
        for row in rows:
            s=(inner.asos_air_temp.le(0).to_numpy(float) if row['candidate']=='asos_air_temp_le_zero'
               else reference_smoothing(inner,inner[row['candidate']+'_score'],int(row['smoothing_minutes'])))
            value=reference_f1(inner,s>=row['threshold'])
            assert abs(value-row['f1_fixed_population'])<1e-12
        selected_rows+=len(q)
        print('독립 검산',outer,flush=True)
    frame=domain(pd.read_parquet(out/'outer_predictions.parquet'))
    for method,report in summary['reports'].items():
        for minimum in [144,130,72,1]:
            assert abs(reference_f1(frame,frame[method],minimum)-report['coverage'][str(minimum)]['f1_fixed_population'])<1e-12
    methods=['pred_current','pred_asos','pred_selected','pred_existing_selected','pred_always_one']
    events={m:event_metrics(frame.rename(columns={m:'predicted_ice'})) for m in methods}
    days=pd.read_csv(out/'daily.csv',dtype={'station':str},parse_dates=['date_kst'])
    stations=sorted(frame.station.unique());dates=pd.date_range('2024-11-01','2025-02-28')
    grid=pd.MultiIndex.from_product([stations,dates],names=['station','date_kst'])
    arrays={m:days.loc[days.method.eq(m)].set_index(['station','date_kst']).f1.reindex(grid).to_numpy().reshape(len(stations),len(dates)) for m in methods}
    rng=np.random.default_rng(20261024);bootstrap={m:[] for m in methods}
    for _ in range(2000):
        starts=rng.integers(0,len(dates),size=int(np.ceil(len(dates)/7)))
        ix=np.concatenate([(s+np.arange(7))%len(dates) for s in starts])[:len(dates)]
        for m,a in arrays.items():
            values=a[:,ix];counts=np.isfinite(values).sum(axis=1)
            means=np.divide(np.nansum(values,axis=1),counts,out=np.zeros(len(stations)),where=counts>0)
            bootstrap[m].append(float(means.mean()))
    comparisons={}
    for baseline in ['pred_current','pred_asos']:
        difference=np.array(bootstrap['pred_selected'])-np.array(bootstrap[baseline])
        comparisons[baseline]=dict(delta=summary['reports']['pred_selected']['coverage']['144']['f1_fixed_population']-summary['reports'][baseline]['coverage']['144']['f1_fixed_population'],
            ci95_low=float(np.quantile(difference,.025)),ci95_high=float(np.quantile(difference,.975)),
            fraction_nonpositive=float(np.mean(difference<=0)))
    assert preservation()==freeze
    audit=dict(status='independent_award_audit_passed',created_at_utc=datetime.now(timezone.utc).isoformat(),
        summary_sha256=sha(out/'summary.json'),new_model_query_scores_replayed=score_rows,outer_selected_rows=selected_rows,
        metric_reports_verified=len(summary['reports'])*4,events=events,
        paired_date_block_bootstrap=dict(block_days=7,repetitions=2000,comparisons=comparisons,
            interpretation='고정 개발 지점·선택된 예측에 조건부인 날짜 변동. 새 지역 일반화나 전체 모델 선택 불확실성의 보장 아님'),
        old_frozen_files=freeze[0],reserved_frozen_files=freeze[1],protected_outcomes_read=False)
    target.write_text(json.dumps(audit,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    print(json.dumps(audit,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
