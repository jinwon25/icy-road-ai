"""G+H+K 제외 보정의 생성 경로·모델·시그모이드·선택·지표를 독립 감사한다."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,sys
import joblib,numpy as np,pandas as pd
from scipy.special import expit
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score,brier_score_loss,log_loss
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.audit_joint_surface import read,sha,identity,close,counts,report,independent_thresholds
from src.validation import normalize_state
from src.external_reserved import verify_reserved_freeze
from src.frozen_assessment import verify_freeze


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',type=Path,required=True);args=parser.parse_args();out=args.experiment.resolve()
    if not out.is_relative_to((ROOT/'outputs/private').resolve()):parser.error('Private experiment required')
    target=out/'independent_verification.json'
    if target.exists():raise FileExistsError('Preserve audit')
    plan=read(out/'experiment_plan.json');summary=read(out/'summary.json');sig=read(out/'input_signature.json')
    assert sha(out/'experiment_plan.json')==summary['plan_sha256']
    assert sha(out/'analysis_source.py')==sha(ROOT/'scripts/evaluate_score_calibration.py')
    assert sha(out/'calibration_source.py')==sha(ROOT/'src/score_calibration.py')
    for r in sig.values():assert sha(r['path'])==r['sha256']
    old=Path(sig['previous_receipts']['path']).parent
    for r in read(old/'input_signature.json').values():assert sha(r['path'])==r['sha256']
    index=pd.read_parquet(sig['index']['path']);temp=pd.read_parquet(sig['temperature_index']['path']);raw=pd.read_parquet(sig['features']['path'])
    assert index.time.ge('2024-11-01').all() and index.time.lt('2025-03-01').all()
    assert not set(index.station)&{'12410','33411','23402'} and not index.duplicated(['station','time']).any()
    np.testing.assert_allclose(index.ice,index.state_raw.map(normalize_state),rtol=0,atol=0,equal_nan=True)
    pd.testing.assert_frame_equal(index[['station','time','group']],temp[['station','time','group']])
    old_plan=read(sig['previous_plan']['path']);features=old_plan['features'];weather=old_plan['regression_features'];params=plan['parameters']
    receipts=read(out/'fit_receipts.json');old_receipts=read(sig['previous_receipts']['path']);models={};refits=[]
    domain=np.isfinite(temp.road_temp)&raw.asos_air_temp.notna();blocks=read(old/'unit_blocks.json');auxiliary_rows=0;classifier_rows=0
    for r in old_receipts+receipts:
        assert sha(r['model_path'])==r['model_sha256'];model=joblib.load(r['model_path']);models[r['model_sha256']]=model
        assert list(model.feature_names_in_)==r['features'] and all(model.get_params()[k]==v for k,v in params.items())
        assert not set(r['training_stations'])&set(r['forbidden_stations'])
        if r in receipts and r['kind']=='temperature':
            mask=domain&~index.station.isin(r['forbidden_stations']);assert int(mask.sum())==r['training_rows']
            assert identity(temp.loc[mask,['station','time','road_temp']])==r['training_identity']
            if not r['reused'] and 'temperature' not in refits:
                clone=HistGradientBoostingRegressor(**params)
                with threadpool_limits(limits=2):
                    clone.fit(raw.loc[mask,weather],temp.loc[mask,'road_temp']);np.testing.assert_allclose(clone.predict(raw.loc[mask,weather].iloc[:1000]),model.predict(raw.loc[mask,weather].iloc[:1000]),atol=0,rtol=0)
                refits.append('temperature')
    contexts={}
    for name,r in sig.items():
        if name.startswith('context_'):
            q=pd.read_parquet(r['path']);contexts[tuple(sorted(q.group.unique()))]=q
    def matrix(ids,t):
        x=raw.loc[ids,weather+['rain15_max_3h','asos_snow_cm']].copy();x['estimated_weather_temp']=t
        x['estimated_surface_dewpoint_gap']=t-x.aws_dewpoint;x['estimated_surface_air_gap']=t-x.aws_air_temp
        wet=(x.aws_dewpoint.ge(t)|x.rain15_max_3h.gt(0)|x.asos_snow_cm.gt(0)).astype(float)
        x['moisture_evidence']=wet.mask(x[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].isna().all(axis=1)|~np.isfinite(t));return x[features]
    for folder in sorted((out/'contexts').iterdir()):
        p=read(folder/'auxiliary_receipts.json');held=tuple(p['held_groups']);forbidden=set(index.loc[index.group.isin(held),'station']);mask=index.ice.notna()&~index.station.isin(forbidden)
        saved=pd.read_parquet(folder/'training_features.parquet');saved.index=pd.Index(saved.original_index,name=None)
        saved.index.name=None
        assert saved.original_index.tolist()==index.index[mask].tolist();pd.testing.assert_frame_equal(saved[index.columns],index.loc[mask],check_index_type=False)
        for a in p['auxiliary']:
            r=a['receipt'];block=a['block'];assert set(r['forbidden_stations'])==forbidden|{st for st,b in blocks.items() if b==block}
            ids=saved.index[saved.auxiliary_block.eq(block)]
            assert not set(index.loc[ids,'station'])&set(r['training_stations'])
            with threadpool_limits(limits=2):t=models[r['model_sha256']].predict(raw.loc[ids,weather])
            t=np.where(raw.loc[ids].asos_air_temp.notna(),t,np.nan);np.testing.assert_allclose(saved.loc[ids,'estimated_weather_temp'],t,rtol=0,atol=0,equal_nan=True);auxiliary_rows+=len(ids)
        pd.testing.assert_frame_equal(saved[features],matrix(saved.index,saved.estimated_weather_temp.to_numpy()),check_index_type=False)
        q=pd.read_parquet(folder/'query_predictions.parquet');ids=q.original_index.to_numpy();assert ids.tolist()==index.index[index.station.isin(forbidden)].tolist()
        pd.testing.assert_frame_equal(q[index.columns].reset_index(drop=True),index.loc[ids].reset_index(drop=True))
        assert set(p['full']['forbidden_stations'])==forbidden
        with threadpool_limits(limits=2):t=models[p['full']['model_sha256']].predict(raw.loc[ids,weather])
        t=np.where(raw.loc[ids].asos_air_temp.notna(),t,np.nan);np.testing.assert_allclose(q.estimated_weather_temp,t,atol=0,rtol=0,equal_nan=True)
        np.testing.assert_array_equal(q.fallback,~np.isfinite(t));r=next(r for r in receipts if r['kind']=='classifier' and r['context_groups']==list(held))
        assert set(r['forbidden_stations'])==forbidden and r['matrix_sha256']==sha(folder/'training_features.parquet')
        assert r['training_rows']==len(saved) and r['positives']==int(saved.ice.sum()) and r['training_identity']==identity(saved)
        x=matrix(ids,t);model=models[r['model_sha256']]
        with threadpool_limits(limits=2):score=model.predict_proba(x)[:,list(model.classes_).index(1)]
        np.testing.assert_allclose(q.binary_thermal_weather_score,np.where(q.fallback,q.baseline_score,score),atol=0,rtol=0)
        if 'classifier' not in refits:
            clone=HistGradientBoostingClassifier(**params)
            with threadpool_limits(limits=2):
                clone.fit(saved[features],saved.ice.astype(int),sample_weight=np.where(saved.ice.eq(1),20.,1.));np.testing.assert_allclose(clone.predict_proba(x),model.predict_proba(x),atol=0,rtol=0)
            refits.append('classifier')
        contexts[held]=q;classifier_rows+=len(q);print('Audited triple context:',held,flush=True)
    all_receipts=old_receipts+receipts;groups=sorted(set(index.group)-{'competition'})
    def scored(held,target_groups):
        q=contexts[held].loc[lambda d:d.group.isin(target_groups)].copy();r=next(r for r in all_receipts if r['kind']=='classifier' and r['candidate']=='binary_thermal_weather' and r['context_groups']==list(held))
        train=index.ice.notna()&~index.group.isin(held);prior=float(index.loc[train,'ice'].mean());assert int(train.sum())==r['training_rows']
        score=np.clip(q.binary_thermal_weather_score.to_numpy(),1e-9,1-1e-9);q['raw_logit']=np.log(score/(1-score));q['prior_logit']=q.raw_logit-np.log(20)-np.log(prior/(1-prior))
        q['training_prevalence']=prior;q['source_model_sha256']=r['model_sha256'];q['source_forbidden_groups']=[list(held)]*len(q);return q
    calibration_rows=0;calibrators={}
    for folder in sorted((out/'calibrations').iterdir()):
        r=read(folder/'receipt.json');held=tuple(r['held_groups']);pool=pd.read_parquet(folder/'training_predictions.parquet')
        expected=pd.concat([scored(tuple(sorted([*held,k])),[k]) for k in groups if k not in held]);expected=expected[expected.ice.notna()&~expected.fallback]
        assert sha(folder/'training_predictions.parquet')==r['training_predictions_sha256']
        assert set(pool)==set(expected)
        pd.testing.assert_frame_equal(pool.reset_index(drop=True),expected[pool.columns].reset_index(drop=True),rtol=0,atol=1e-12)
        assert not set(pool.group)&set(held) and not pool.duplicated(['station','time']).any()
        assert all(set(held)|{a.group}==set(a.source_forbidden_groups) for a in pool[['group','source_forbidden_groups']].itertuples(index=False))
        assert r['training_rows']==len(pool) and r['positives']==int(pool.ice.sum())
        for variant in ['raw','prior']:
            fit=r[variant];x=pool[variant+'_logit'].to_numpy();y=pool.ice.to_numpy();a=fit['slope'];b=fit['intercept'];assert a>=0
            assert fit['source_identity']==hashlib.sha256(np.column_stack([x,y]).tobytes()).hexdigest()
            z=a*x+b;e=expit(z)-y;objective=float(np.logaddexp(0,z).sum()-y@z+.5*a*a)
            assert abs(objective-fit['objective'])<1e-8
            # 볼록 목적함수의 경계 KKT 조건. 합산 경사보다 표본당 경사로 수렴 오차를 확인한다.
            assert abs(e.sum())/len(y)<1e-7
            gradient=e@x+a
            assert (gradient>=-1e-3 if a==0 else abs(gradient)/len(y)<1e-7)
        calibrators[held]=r;calibration_rows+=len(pool)
    def prediction(held,target_groups):
        q=scored(held,target_groups);r=calibrators[held];q['prior_score_score']=expit(q.prior_logit)
        for name,variant in [('calibrated_raw','raw'),('calibrated_prior','prior')]:q[name+'_score']=expit(r[variant]['slope']*q[variant+'_logit']+r[variant]['intercept'])
        for c in plan['candidates']:q[c+'_score']=np.where(q.fallback,q.baseline_score,q[c+'_score'])
        return q
    decisions=read(out/'decisions.json');outer=pd.read_parquet(out/'outer_predictions.parquet');seal=read(out/'prediction_seal.json')
    assert sha(out/'outer_predictions.parquet')==seal['sha256'] and sha(out/'decisions.json')==seal['decisions_sha256'];threshold_rows=0
    for g,d in decisions.items():
        assert d['decided_at_utc']<seal['timestamp_utc'] and not d['outer_labels_used']
        inner=pd.concat([prediction(tuple(sorted([g,h])),[h]) for h in groups if h!=g]);br,bs=report(inner,inner.thermal_moisture)
        for k,v in br.items():close(v,d['baseline'][k])
        eligible=[]
        for c in plan['candidates']:
            table=independent_thresholds(inner,inner[c+'_score'],inner.fallback,inner.baseline_prediction);saved=pd.read_csv(out/'decisions'/(g+'__'+c+'__thresholds.csv'))
            np.testing.assert_allclose(table,saved[table.columns],atol=1e-12,rtol=0);threshold_rows+=len(table)
            threshold=table[table.fp.le(br['fp'])].sort_values(['fixed_ice_day_f1','f1','threshold'],ascending=False).iloc[0].threshold;close(threshold,d['thresholds'][c])
            p=np.where(inner.fallback,inner.baseline_prediction,inner[c+'_score']>=threshold).astype(int);cr,cs=report(inner,p)
            for k,v in cr.items():close(v,d['candidates'][c][k])
            checks=dict(f1_guards=all((cr[k] or 0)+1e-12>=(br[k] or 0) for k in ['f1','fixed_ice_day_f1','fixed_station_f1_zero_undefined']),strict_improvement=any((cr[k] or 0)>(br[k] or 0)+1e-12 for k in ['f1','fixed_ice_day_f1']),false_alarm_budget=cr['fp']<=br['fp'],single_slot_guard=cr['detected_single_slot_events']>=br['detected_single_slot_events'],station_recall_guard=all(cs[s]['tp']>=bs[s]['tp'] for s in bs if bs[s]['tp']+bs[s]['fn']>=5))
            assert checks==d['guards'][c]
            if all(checks.values()):eligible.append(c)
        selected=min(eligible,key=lambda c:(-d['candidates'][c]['fixed_ice_day_f1'],-d['candidates'][c]['f1'],c)) if eligible else 'thermal_moisture'
        assert d['selected']==selected and d['eligible']==eligible
        q=prediction((g,),[g]);output=outer[outer.group.eq(g)]
        for c in plan['candidates']:
            np.testing.assert_allclose(output[c+'_score'],q[c+'_score'],rtol=0,atol=1e-14)
            np.testing.assert_array_equal(output[c],np.where(q.fallback,q.baseline_prediction,q[c+'_score']>=d['thresholds'][c]).astype(int))
        np.testing.assert_array_equal(output.selected_prediction,output[selected])
    assert outer.original_index.tolist()==index.index[index.group.ne('competition')].tolist()
    pd.testing.assert_frame_equal(outer[index.columns].reset_index(drop=True),index.loc[index.group.ne('competition')].reset_index(drop=True))
    for p,expected in summary['metrics'].items():
        actual,_=report(outer,outer[p]);valid=outer.ice.notna()
        if p in plan['candidates']:
            actual['average_precision']=float(average_precision_score(outer.loc[valid,'ice'],outer.loc[valid,p+'_score']))
            if p.startswith('calibrated'):
                actual['brier']=float(brier_score_loss(outer.loc[valid,'ice'],outer.loc[valid,p+'_score']));actual['log_loss']=float(log_loss(outer.loc[valid,'ice'],outer.loc[valid,p+'_score']))
        assert actual.keys()==expected.keys()
        for k,v in actual.items():close(v,expected[k])
    release=ROOT/'outputs/private/releases/20261007';reserved=verify_reserved_freeze(release,release/'outputs/private/external_reserved_predictions_v1');original=verify_freeze(release)
    result=dict(status='passed',checked_at_utc=datetime.now(timezone.utc).isoformat(),new_fit_receipts=len(receipts),auxiliary_training_predictions=auxiliary_rows,classifier_query_scores=classifier_rows,calibration_training_rows=calibration_rows,calibrators=len(calibrators)*2,threshold_rows=threshold_rows,representative_refits=refits,outer_rows=len(outer),policies=len(summary['metrics']),original_frozen_files=len(original['files']),reserved_frozen_files=len(reserved['files']),summary_sha256=sha(out/'summary.json'),source_sha256=sha(__file__))
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
