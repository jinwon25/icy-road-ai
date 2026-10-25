"""기존 개발 9지점에서 API 형식 통일의 영향을 지역 제외로 진단한다. 새 정답 접근 없음."""
from pathlib import Path
import sys
import warnings
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.blind_icing_validation import DEFAULT,PRIVATE,read,write,now,predict,verify
from src.anchored_icing import linear_features
from src.synoptic_icing import sample_weights
from src.blind_icing import daily_metrics,summarize_days,event_table
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.audit_icing_transition import independent_metrics,independent_events
from scripts.fresh_station_validation import old_freezes


def main():
    out=PRIVATE/'asos_parity_development_20261025_v1'
    if out.exists():raise FileExistsError('Preserve development diagnostic')
    out.mkdir(parents=True);verify(DEFAULT);plan=read(DEFAULT/'plan.json')
    f=pd.read_parquet(DEFAULT/'training.parquet');assert set(f.station).isdisjoint(plan['new_stations'])
    write(out/'plan.json',dict(created_at_utc=now(),data_sha256=sha(DEFAULT/'training.parquet'),settings=plan,
        frozen_new_predictions_sha256=sha(DEFAULT/'predictions.parquet'),code_sha256=sha(Path(__file__)),
        purpose='Old four-group development diagnostic only; fixed new-site candidates and predictions cannot change',new_outcomes_read=False))
    parts=[];receipts=[]
    for held in sorted(set(f.group)-{'competition'}):
        tm=~f.group.eq(held)&f.available&f.ice.isin([0,1]);query=f.loc[f.group.eq(held)].copy();train=f.loc[tm]
        models={'logit_day_anchor1':make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler(),LogisticRegression(**plan['logistic_parameters'])),
            'hgb_day_anchor1':HistGradientBoostingClassifier(**plan['hgb_parameters'])}
        assert set(train.station).isdisjoint(query.station)
        for name,model in models.items():
            w=sample_weights(train,'day');kwargs={'logisticregression__sample_weight':w} if name.startswith('logit') else {'sample_weight':w}
            with warnings.catch_warnings(),deny_network() as attempts,threadpool_limits(limits=2):
                warnings.simplefilter('error',ConvergenceWarning);model.fit(linear_features(train),train.ice.to_numpy(int),**kwargs)
            assert not attempts;path=out/(held+'__'+name+'.joblib');joblib.dump(model,path,compress=3)
            receipts.append(dict(held=held,candidate=name,train_rows=len(train),train_stations=sorted(train.station.unique()),query_stations=sorted(query.station.unique()),model_sha256=sha(path)))
            print('DEVELOPMENT FIT',held,name,flush=True)
        q=predict(query,models);q['ice']=query.ice.to_numpy();q['group']=held;parts.append(q)
    f=pd.concat(parts,ignore_index=True).sort_values(['station','time']).reset_index(drop=True);pop=sorted(f.station.unique());assert len(pop)==9
    f.to_parquet(out/'predictions.parquet',index=False,compression='zstd');reports={};checks=0
    for name in plan['candidate_names']:
        reports[name]={}
        for year in ['all',2024,2025]:
            part=f if year=='all' else f.loc[f.winter.eq(year)]
            winters=plan['winters'] if year=='all' else [w for w in plan['winters'] if w[0].startswith(str(year))]
            r=summarize_days(daily_metrics(part,part[name],pop,winters),pop)
            other=independent_metrics(part,part[name])
            for k in ['f1_fixed_population','precision_available_station_mean','recall_available_station_mean','fp','fn','tp']:
                if r[k] is None:assert other[k] is None
                else:np.testing.assert_allclose(r[k],other[k],atol=1e-12,rtol=0)
            reports[name][str(year)]=r;checks+=1
        r,_=event_table(f,f[name],f.asos_zero);assert r==independent_events(f,f[name],f.asos_zero);reports[name]['events']=r
    # 저장 모델을 별도 호출로 재추론하여 모든 저장값과 대조한다.
    source=pd.read_parquet(DEFAULT/'training.parquet')
    for receipt in receipts:
        query=source.loc[source.group.eq(receipt['held'])];model=joblib.load(out/(receipt['held']+'__'+receipt['candidate']+'.joblib'))
        with deny_network() as attempts,threadpool_limits(limits=2):score=model.predict_proba(linear_features(query))[:,1]
        assert not attempts
        actual=f.loc[f.group.eq(receipt['held']),receipt['candidate']+'_score'];np.testing.assert_array_equal(score,actual)
    verify(DEFAULT)
    write(out/'summary.json',dict(status='old_region_parity_diagnostic_complete',completed_at_utc=now(),reports=reports,
        fits=receipts,metric_checks=checks,models_replayed=len(receipts),new_outcomes_read=False,
        new_independent_assessment=False,candidate_or_frozen_prediction_changed=False,frozen_counts=list(old_freezes()),
        predictions_sha256=sha(out/'predictions.parquet')))


if __name__=='__main__':main()
