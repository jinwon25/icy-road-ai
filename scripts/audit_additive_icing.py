"""저장 모델·학습 분리·전처리·가중치·내부 후보 전체와 선택을 별도로 검산한다."""
from collections import Counter,defaultdict
from pathlib import Path
import sys
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.blind_icing_validation import DEFAULT,verify,read,write,now,old_freezes
from scripts.audit_icing_transition import independent_metrics
from src.anchored_icing import linear_features
from src.synoptic_icing import sample_weights
from src.offline_runtime import deny_network
from src.data_source import sha256_file as sha


def main():
    plan=read(ROOT/'config/additive_icing_20261025.json');out=ROOT/plan['out'];receipt=read(out/'plan.json');summary=read(out/'summary.json')
    if (out/'audit.json').exists():raise FileExistsError('Preserve audit')
    verify(DEFAULT)
    assert receipt['config_sha256']==sha(ROOT/'config/additive_icing_20261025.json')
    assert receipt['source_sha256']==sha(ROOT/plan['source'])
    assert receipt['code_sha256']==sha(ROOT/'scripts/evaluate_additive_icing.py') and receipt['module_sha256']==sha(ROOT/'src/additive_icing.py')
    f=pd.read_parquet(ROOT/plan['source']).sort_values(['station','time']).reset_index(drop=True)
    assert set(f.station).isdisjoint(plan['blocked_stations'])
    for fit in summary['fits']:
        model=joblib.load(out/fit['model_path']);assert sha(out/fit['model_path'])==fit['model_sha256']
        tr=f.loc[~f.group.isin(fit['excluded'])&f.available&f.ice.isin([0,1])&f.asos_air_temp.gt(0)&f.asos_air_temp.le(4)]
        q=f.loc[f.group.isin(fit['excluded'])]
        assert len(tr)==fit['rows'] and int(tr.ice.sum())==fit['positives']
        assert sorted(tr.station.unique())==fit['train_stations'] and set(tr.station).isdisjoint(q.station)
        rows=[(s,int(w),t.date(),int(y)) for s,w,t,y in tr[['station','winter','time','ice']].itertuples(index=False,name=None)]
        counts=Counter(rows);classes=defaultdict(set);dates=defaultdict(set)
        for s,w,d,y in counts:classes[(s,w,d)].add(y);dates[(s,w)].add(d)
        weights=np.array([1/(counts[(s,w,d,y)]*len(classes[(s,w,d)])*len(dates[(s,w)])) for s,w,d,y in rows]);weights/=weights.mean()
        np.testing.assert_allclose(weights,sample_weights(tr,'day'),rtol=0,atol=1e-12)
        x=linear_features(tr)
        if fit['model']=='warm_logit':
            imputer,scaler,_=model.steps
            np.testing.assert_allclose(imputer[1].statistics_,x.median().fillna(0),rtol=0,atol=1e-12)
            transformed=imputer[1].transform(x)
            np.testing.assert_allclose(scaler[1].mean_,transformed.mean(axis=0),rtol=0,atol=1e-10)
        saved=pd.read_parquet(out/('__'.join(fit['excluded'])+'__scores.parquet'))
        pd.testing.assert_frame_equal(saved[['station','time']].reset_index(drop=True),q[['station','time']].reset_index(drop=True))
        with deny_network() as attempts,threadpool_limits(limits=2):score=model.predict_proba(linear_features(q))[:,1]
        assert not attempts;np.testing.assert_array_equal(score,saved[fit['model']])
    metric_checks=0;selection_checks=0
    for selected in summary['selections']:
        held=selected['held'];parts=[]
        for g in selected['inner_groups']:
            q=pd.read_parquet(out/('__'.join(sorted([held,g]))+'__scores.parquet'));parts.append(q.loc[q.group.eq(g)])
        inner=pd.concat(parts,ignore_index=True)
        table=pd.read_csv(out/(held+'__inner_candidates.csv'))
        for row in table.itertuples():
            valid=inner.available.to_numpy(bool);air=inner.asos_air_temp.to_numpy(float)
            pred=air<=0
            if row.candidate!='asos_zero':pred|=(air>0)&(air<=row.cap)&(inner[row.model].to_numpy()>=row.threshold)
            pred=np.where(valid,pred,np.nan)
            for year in ['all',2024,2025]:
                mask=np.ones(len(inner),bool) if year=='all' else inner.winter.eq(year).to_numpy()
                ref=independent_metrics(inner.loc[mask],pred[mask])
                np.testing.assert_allclose(row.f1 if year=='all' else getattr(row,f'f1_{year}'),ref['f1_fixed_population'],rtol=0,atol=1e-12);metric_checks+=1
                if year=='all':
                    for short,long in [('precision','precision_available_station_mean'),('recall','recall_available_station_mean')]:
                        np.testing.assert_allclose(getattr(row,short),ref[long],rtol=0,atol=1e-12);metric_checks+=1
                    for site in sorted(inner.station.unique()):
                        site_mask=inner.station.eq(site).to_numpy()
                        value=independent_metrics(inner.loc[site_mask],pred[site_mask])['f1_fixed_population']
                        np.testing.assert_allclose(getattr(row,'site_'+site),value,rtol=0,atol=1e-12);metric_checks+=1
        base=table.loc[table.candidate.eq('asos_zero')].iloc[0]
        eligible=[]
        for row in table.to_dict('records'):
            if row['f1']>=1.01*base.f1 and row['f1']>base.f1 and row['precision']>=base.precision and all(row[k]>=base[k] for k in ['f1_2024','f1_2025',*[c for c in table if c.startswith('site_')]]):eligible.append(row)
        def choose(rows):return sorted(rows,key=lambda r:(-r['f1'],r['complexity'],r['cap'],-r['threshold'],r['candidate']))[0]['candidate']
        assert (choose(eligible) if eligible else 'asos_zero')==selected['selected']['guarded']
        assert choose(table.to_dict('records'))==selected['selected']['maximum_f1'];selection_checks+=2
    final=pd.read_parquet(out/'predictions.parquet');assert sha(out/'predictions.parquet')==summary['predictions_sha256']
    for track in ['guarded','maximum_f1']:
        for selection in summary['selections']:
            part=final.loc[final.group.eq(selection['held'])]
            np.testing.assert_array_equal(part[track],part[selection['selected'][track]])
    verify(DEFAULT);assert old_freezes()==(47,549)
    write(out/'audit.json',dict(status='passed',at_utc=now(),saved_models_replayed=len(summary['fits']),inner_metric_checks=metric_checks,
        selection_checks=selection_checks,preprocessing_and_weights_checked=True,summary_sha256=sha(out/'summary.json'),code_sha256=sha(Path(__file__)),
        new_four_site_training_or_scoring=False,original_blind_summary_sha256=sha(DEFAULT/'summary.json')))
    print('AUDIT PASSED',len(summary['fits']),metric_checks,selection_checks,flush=True)


if __name__=='__main__':main()
