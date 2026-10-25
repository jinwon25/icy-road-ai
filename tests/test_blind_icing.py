import numpy as np
import pandas as pd
import pytest
from src.blind_icing import FIELDS,normalize_weather,daily_metrics,summarize_days,event_table,paired_bootstrap
from src.weather_features import prior_join


def test_negative_temperature_and_sparse_codes_are_distinct():
    raw=pd.DataFrame({k:['-9','0','-99'] for k in FIELDS})
    raw['STN']='203';raw['time']=pd.date_range('2024-11-01',periods=3,freq='h')
    f=normalize_weather(raw)
    assert f.air_temp.iloc[0]==-9 and f.dewpoint_obs.iloc[0]==-9
    assert np.isnan(f.air_temp.iloc[2]) and np.isnan(f.rain_mm.iloc[0]) and f.rain_mm.iloc[1]==0
    assert np.isnan(f.pressure.iloc[1])
    with pytest.raises(ValueError):normalize_weather(pd.concat([raw,raw]))


def test_prior_weather_exact_boundary_and_missing_hour():
    source=pd.DataFrame({'source_time':pd.to_datetime(['2024-11-01 00:00','2024-11-01 02:00']),'air_temp':[1.,3.]})
    target=pd.DataFrame({'time':pd.to_datetime(['2024-11-01 00:00','2024-11-01 01:00','2024-11-01 01:10','2024-11-01 02:00','2024-11-01 02:10'])})
    f=prior_join(target,source,'asos')
    np.testing.assert_array_equal(f.asos_air_temp,[np.nan,1.,np.nan,np.nan,3.])


def sample():
    return pd.DataFrame({'station':'a','time':pd.date_range('2024-11-01',periods=288,freq='10min'),'ice':0.})


def test_fixed_population_missing_days_and_undefined_recall():
    f=sample();p=np.zeros(len(f));p[0]=1;f.loc[144,'ice']=1
    d=daily_metrics(f,p,['a','empty'],[['2024-11-01','2024-11-03']])
    r=summarize_days(d,['a','empty'])
    assert len(d)==4 and r['complete_or_accepted_days']==2 and r['f1_fixed_population']==0
    a=d.loc[d.station.eq('a')]
    assert np.isnan(a.recall.iloc[0]) and a.recall.iloc[1]==0
    assert a.precision.iloc[0]==0 and np.isnan(a.precision.iloc[1])
    assert d.loc[d.station.eq('empty'),'f1'].isna().all()


def test_partial_day_sensitivity_and_invalid_labels():
    f=sample().iloc[:143].copy();f.loc[0,'ice']=1;p=np.zeros(len(f));p[0]=1
    args=(f,p,['a'],[['2024-11-01','2024-11-02']])
    assert summarize_days(daily_metrics(*args,72),['a'])['f1_fixed_population']==1
    assert summarize_days(daily_metrics(*args,144),['a'])['f1_fixed_population']==0
    f.loc[0,'ice']=4
    with pytest.raises(ValueError):daily_metrics(*args)


def test_events_separate_missing_time_and_sites_and_record_losses():
    f=pd.DataFrame({'station':['a','a','a','a','b'],'time':pd.to_datetime(['2024-11-01 00:00','2024-11-01 00:10','2024-11-01 00:30','2024-11-01 00:40','2024-11-01 00:40']),'ice':[1,1,1,0,1]})
    r,e=event_table(f,[0,0,1,1,1],[1,1,0,0,1])
    assert r==dict(observed_events=3,baseline_detected=2,candidate_detected=2,lost_events=1,gained_events=1)
    assert e.slots.tolist()==[2,1,1]


def test_bootstrap_uses_paired_dates_and_reproducible_zero():
    f=sample();f.loc[0,'ice']=1;p=f.ice.to_numpy()
    d=daily_metrics(f,p,['a'],[['2024-11-01','2024-11-03']])
    r=paired_bootstrap(d,d,['a'],draws=50)
    assert r['difference_ci95']==[0.,0.] and r['positive_fraction']==0


def test_complete_evaluation_detects_primary_loss_without_changing_candidate(tmp_path,monkeypatch):
    """정답 개봉 전 합성 4지역·두 겨울로 실제 평가 경로와 사전 성공 기준을 검증한다."""
    from scripts import blind_icing_validation as run
    plan=run.read(run.CONFIG);run.write(tmp_path/'plan.json',plan)
    dates=pd.DatetimeIndex(np.concatenate([pd.date_range(a,b,freq='10min',inclusive='left').values for a,b in plan['winters']]))
    q=pd.MultiIndex.from_product([plan['new_stations'],dates],names=['station','time']).to_frame(index=False)
    q['winter']=np.where(q.time.dt.month.ge(11),q.time.dt.year,q.time.dt.year-1);q['available']=True;q['asos_air_temp']=-1.
    for name in plan['candidate_names']:q[name]=1.
    q[plan['primary_candidate']]=0.
    q.to_parquet(tmp_path/'predictions.parquet',index=False)
    g=q[['station','time']].copy();g['ice']=0.;g.loc[g.time.dt.hour.eq(0)&g.time.dt.minute.eq(0),'ice']=1.
    g['state_raw']=np.where(g.ice.eq(1),'04','01');g['road_temp']=-1.;g['lat']=35.;g['lon']=127.
    (tmp_path/'observations').mkdir();records={}
    for (s,d),part in g.groupby(['station',g.time.dt.normalize()]):
        key=f'{s}_{d:%Y%m%d%H%M}';path=tmp_path/'observations'/(key+'.parquet');part.to_parquet(path,index=False)
        records[key]={'sha256':run.sha(path)}
    assert len(records)==960
    run.write(tmp_path/'download_manifest.json',dict(status='complete',records=records))
    run.write(tmp_path/'prediction_seal.json',{})
    pd.DataFrame({'station':plan['new_stations'],'lat':35.,'lon':127.}).to_csv(tmp_path/'points.csv',index=False)
    monkeypatch.setattr(run,'verify',lambda p:{})
    monkeypatch.setattr(run,'old_freezes',lambda:(47,549))
    run.evaluate(tmp_path);r=run.read(tmp_path/'summary.json')
    assert r['primary_candidate']=='logit_day_anchor1' and not r['primary_success']
    assert r['primary_gates']['coverage'] and r['primary_gates']['positive_sites']
    assert r['reports']['logit_day_anchor1']['events']['lost_events']==960
    assert r['reports']['hgb_day_anchor1']['144']['f1_fixed_population']>0
    with pytest.raises(FileExistsError):run.evaluate(tmp_path)
