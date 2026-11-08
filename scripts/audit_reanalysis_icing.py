"""새 지표면 분류기의 전체 재추론·독립 임계값 곡선·외부 지표를 대조한다."""
from pathlib import Path
import gc
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_reanalysis_inputs import read, write
from scripts.evaluate_objective_icing import verify_preserved
from scripts.audit_objective_icing import independent_features, independent_weights, same
from scripts.audit_icing_transition import independent_metrics, independent_events
from src.vectorized_daily_threshold import threshold_curve, select_threshold
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def independent_choice(rows, track):
    maximum = max(row[track] for row in rows)
    tied = [row for row in rows if abs(row[track] - maximum) <= 1e-12]
    return min(tied, key=lambda row: (row['complexity'], row['fp'], -row['threshold'], row['candidate']))


def main():
    study = ROOT / 'outputs/private/reanalysis_icing_20261031_v1'
    target = study / 'independent_verification.json'
    if target.exists(): raise FileExistsError('Preserve first completed audit')
    plan = read(study/'plan.json'); settings = plan['settings']; summary = read(study/'summary.json')
    for name, digest in plan['signatures'].items(): assert sha(ROOT/name) == digest, name
    for name, digest in summary['files'].items(): assert sha(study/name) == digest, name
    assert verify_preserved() == plan['preservation']
    f = pd.read_parquet(ROOT/settings['asos_source']).sort_values(['station','time']).reset_index(drop=True)
    raw = ['era5_'+name for name in ['temperature_2m','relative_humidity_2m','dew_point_2m',
        'soil_temperature_0_to_7cm','soil_temperature_7_to_28cm','soil_moisture_0_to_7cm','soil_moisture_7_to_28cm','snow_depth']]
    memory = raw + ['era5_'+name+'_mean'+str(hours)+'h' for name in
        ['temperature_2m','soil_temperature_0_to_7cm','soil_moisture_0_to_7cm','snow_depth'] for hours in [6,24,72]]
    extra = pd.read_parquet(ROOT/settings['reanalysis_source'], columns=['station','time','ice',*memory])
    extra = extra.sort_values(['station','time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(f[['station','time','ice']],extra[['station','time','ice']],check_exact=True)
    assert not set(f.station) & set(settings['blocked_stations']) and f.station.nunique() == 23
    base = independent_features(f).iloc[:,:15]
    groups = sorted(set(f.group)-{'competition'})
    replay_values = 0; refits = 0; maximum_error = 0.
    for candidate in settings['candidates']:
        columns = [] if candidate == 'asos15' else raw if candidate == 'era5_raw' else memory
        x = pd.concat([base,extra[columns]],axis=1)
        for record in [r for r in summary['fits'] if r['candidate'] == candidate]:
            excluded = record['excluded']; stem = '__'.join(excluded)
            train = f.loc[~f.group.isin(excluded)&f.available&f.ice.isin([0,1])]
            query = f.loc[f.group.isin(excluded)]
            assert record['training_stations'] == sorted(train.station.unique()) and record['training_rows'] == len(train)
            assert not set(train.station) & set(query.station) and list(x) == record['features']
            model = joblib.load(study/candidate/(stem+'.joblib')); assert model.get_params() == record['parameters']
            for key,value in settings['model'].items(): assert model.get_params()[key] == value
            score = pd.read_parquet(study/candidate/(stem+'.parquet'))
            pd.testing.assert_frame_equal(query[score.columns.drop('score')].reset_index(drop=True),
                                          score.drop(columns='score').reset_index(drop=True),check_exact=True)
            with deny_network() as attempts,threadpool_limits(limits=2):
                values = model.predict_proba(x.loc[query.index])[:,1]
                # 원 기상 대조군과 추가 입력 주 후보를 각각 첫 지역에서 독립 가중치로 재학습한다.
                if candidate in ['asos15','era5_raw'] and excluded == [groups[0]]:
                    repeat = HistGradientBoostingClassifier(**settings['model'])
                    repeat.fit(x.loc[train.index],train.ice.to_numpy(int),sample_weight=independent_weights(train))
                    np.testing.assert_allclose(repeat.predict_proba(x.loc[query.index])[:,1],values,rtol=0,atol=1e-12)
                    del repeat; refits += 1
            assert not attempts
            np.testing.assert_array_equal(values,score.score.to_numpy())
            maximum_error = max(maximum_error,float(np.max(np.abs(values-score.score))))
            replay_values += len(values)
            del train,query,model,score
            gc.collect()
            print('AUDIT MODEL',candidate,stem,flush=True)
        del x
    del f,extra,base
    gc.collect()
    result = pd.read_parquet(study/'predictions.parquet')
    threshold_points = 0; nested_choices = 0; metric_checks = 0
    for decision in summary['decisions']:
        held = decision['held']; tables = read(study/(held+'__inner_selection.json'))
        outer = result.loc[result.group.eq(held)].reset_index(drop=True)
        for candidate in settings['candidates']:
            inner_parts = []
            for other in groups:
                if other == held: continue
                q = pd.read_parquet(study/candidate/('__'.join(sorted([held,other]))+'.parquet'))
                inner_parts.append(q.loc[q.group.eq(other)])
            inner = pd.concat(inner_parts,ignore_index=True)
            assert not set(inner.station) & set(outer.station)
            curve = threshold_curve(inner,np.where(inner.available,inner.score,np.nan))
            threshold_points += len(curve)
            predictions = pd.read_parquet(study/candidate/(held+'.parquet'))
            pd.testing.assert_frame_equal(predictions[['station','time']],outer[['station','time']],check_exact=True)
            for track,rows in tables.items():
                record = next(r for r in rows if r['candidate'] == candidate)
                selected = select_threshold(curve,track)
                for key in ['threshold','mean_f1','worst_winter_f1','tp','fp','fn']: same(selected[key],record[key])
                assert record['unique_thresholds'] == len(curve)
                p = np.where(predictions.available,predictions.score.ge(record['threshold']),np.nan)
                np.testing.assert_array_equal(p,outer[candidate+'_'+track])
                binary = np.where(inner.available,inner.score.ge(record['threshold']),np.nan)
                m = independent_metrics(inner,binary)
                for key in ['tp','fp','fn']: same(m[key],record[key])
                same(m['f1_fixed_population'],record['mean_f1'])
                years = [independent_metrics(inner.loc[inner.winter.eq(y)],binary[inner.winter.eq(y)])['f1_fixed_population'] for y in [2024,2025]]
                same(min(years),record['worst_winter_f1']); metric_checks += 11
                if candidate == 'asos15':
                    baseline = next(r for r in rows if r['candidate'] == 'asos_zero')
                    p0 = np.where(inner.available,inner.asos_air_temp.le(0),np.nan)
                    m0 = independent_metrics(inner,p0)
                    for key in ['tp','fp','fn']: same(m0[key],baseline[key])
                    same(m0['f1_fixed_population'],baseline['mean_f1'])
                    winters = [independent_metrics(inner.loc[inner.winter.eq(y)],p0[inner.winter.eq(y)])['f1_fixed_population'] for y in [2024,2025]]
                    same(min(winters),baseline['worst_winter_f1']); metric_checks += 5
        np.testing.assert_array_equal(outer.asos_zero,np.where(outer.available,outer.asos_air_temp.le(0),np.nan))
        for track,rows in tables.items():
            for label,eligible in [('selected_',rows),('baseline_',[r for r in rows if r['candidate'] in ['asos_zero','asos15']])]:
                chosen = independent_choice(eligible,track)
                assert chosen == decision['choices'][label+track]
                column = 'asos_zero' if chosen['candidate']=='asos_zero' else chosen['candidate']+'_'+track
                np.testing.assert_array_equal(outer[label+track],outer[column]); nested_choices += 1
        print('AUDIT THRESHOLDS',held,threshold_points,flush=True)
    base_days = pd.read_csv(study/'asos_zero__daily.csv')
    for name,report in summary['reports'].items():
        for label,q in [('all',result),*[(str(y),result.loc[result.winter.eq(y)]) for y in [2024,2025]],
                        *[(g,result.loc[result.group.eq(g)]) for g in groups]]:
            expected = report['all'] if label=='all' else report['winters'][label] if label.isdigit() else report['regions'][label]
            for key,value in independent_metrics(q,q[name]).items(): same(value,expected[key]); metric_checks += 1
        assert independent_events(result,result[name],result.asos_zero) == report['events']
        days = pd.read_csv(study/(name+'__daily.csv'))
        assert days[['station','date_kst']].equals(base_days[['station','date_kst']])
        values = []
        for station in sorted(base_days.station.unique()):
            mask = base_days.station.eq(station)&base_days.f1.notna()
            values.append(float(days.loc[mask,'f1'].fillna(0).mean()) if mask.any() else 0.)
        same(float(np.mean(values)),report['baseline_calendar_f1'])
    primary=summary['reports'][settings['primary_track']]
    baseline=summary['reports']['asos_zero']; matched=summary['reports']['baseline_mean_f1']
    gates=dict(f1_asos=primary['all']['f1_fixed_population']>=1.01*baseline['all']['f1_fixed_population'],
        f1_matched=primary['all']['f1_fixed_population']>=1.01*matched['all']['f1_fixed_population'],
        precision=primary['all']['precision_available_station_mean'] is not None and primary['all']['precision_available_station_mean']>=baseline['all']['precision_available_station_mean'],
        recall=primary['all']['recall_available_station_mean'] is not None and primary['all']['recall_available_station_mean']>=baseline['all']['recall_available_station_mean'],
        winters=all(primary['winters'][y]['f1_fixed_population']>=baseline['winters'][y]['f1_fixed_population'] for y in baseline['winters']),
        regions=all(primary['regions'][g]['f1_fixed_population']>=baseline['regions'][g]['f1_fixed_population'] for g in groups),
        stations=all(primary['all']['station_f1_fixed'][s]>=baseline['all']['station_f1_fixed'][s] for s in baseline['all']['station_f1_fixed']),
        events=primary['events']['lost_events']==0,fixed_calendar=primary['baseline_calendar_f1']>=baseline['baseline_calendar_f1'])
    assert gates==summary['gates'] and all(gates.values())==summary['primary_success']
    days=pd.read_csv(study/(settings['primary_track']+'__daily.csv'))
    samples=[]
    starts=[np.random.default_rng(settings['seed']+i).integers(0,120,size=(2000,18)) for i in [0,1]]
    a=days.f1.to_numpy().reshape(-1,240); b=base_days.f1.to_numpy().reshape(-1,240)
    for i in range(2000):
        indices=[]
        for season in [0,1]:
            indices.extend([int((start+j)%120+120*season) for start in starts[season][i] for j in range(7)][:120])
        means=[]
        for values in [a,b]:
            selected=values[:,indices];counts=np.isfinite(selected).sum(axis=1)
            means.append(np.divide(np.nansum(selected,axis=1),counts,out=np.zeros(len(selected)),where=counts>0).mean())
        samples.append(means[0]-means[1])
    expected=summary['sensitivity']
    np.testing.assert_allclose(np.quantile(samples,[.025,.5,.975]),expected['difference_percentiles'],rtol=0,atol=1e-12)
    same(float(np.mean(np.array(samples)>0)),expected['fraction_positive'])
    assert verify_preserved() == plan['preservation']
    write(target,dict(status='passed',model_files=len(summary['fits']),replay_values=replay_values,
        maximum_prediction_error=maximum_error,deterministic_refits=refits,threshold_points=threshold_points,
        nested_choices=nested_choices,metric_checks=metric_checks,event_checks=len(summary['reports']),
        gate_checks=len(gates),block_resampling_checks=2000,
        fixed_calendar_checks=len(summary['reports']),summary_sha256=sha(study/'summary.json'),
        audit_script_sha256=sha(Path(__file__)),threshold_audit_sha256=sha(ROOT/'src/vectorized_daily_threshold.py'),
        preservation=plan['preservation'],protected_outcomes_read=False,new_four_site_outcomes_read=False))
    print('AUDIT COMPLETE',replay_values,'scores',threshold_points,'thresholds',flush=True)


if __name__=='__main__': main()
