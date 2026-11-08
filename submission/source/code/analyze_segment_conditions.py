"""추정 기상·노면온도·조건 빈도의 연관성과 개발 지점 실제 Ice의 조건별 분포를 분리한다."""
from pathlib import Path
from itertools import product
import sys,json,shutil,argparse
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.evidence_hash import sha
def write(p,x):
    with p.open('x',encoding='utf8') as out:json.dump(x,out,ensure_ascii=False,indent=2,allow_nan=False);out.write('\n')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    O=a.output;O.mkdir(parents=True);B=ROOT
    daily_path=B/'results/weather/weather_segment_daily.parquet'
    calendar_path=ROOT/'data/prediction_group_daily.csv.gz'
    sections_path=B/'results/sections/section_review.csv'
    development_path=B/'results/evaluation/development_predictions.parquet'
    write(O/'plan.json',dict(estimated_conditions='same KST daily weather means versus estimated daily road temperature and cold/wet fraction; descriptive Pearson and Spearman, no p-values',
        observation_conditions='9 development sites, regional held-out Tref predictions and observed Ice; fixed physical temperature bins <=-2, (-2,0], (0,2], >2 C crossed with moisture proxy presence',
        rates='10-minute pooled counts and equal-site mean among sites with denominator; not official daily macro Precision',
        no_causal_claim=True,no_optimised_freezing_threshold=True,protected_observations_used=False,
        signatures={p.relative_to(ROOT).as_posix():sha(p) for p in [daily_path,calendar_path,sections_path,development_path,Path(__file__)]}))
    f=pd.read_parquet(daily_path);f['date']=pd.to_datetime(f.date).dt.normalize()
    f['winter']=np.where(f.date.dt.month>=7,f.date.dt.year,f.date.dt.year-1)
    section=pd.read_csv(sections_path,dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
    f=f.merge(section[['seg_id','winter','prediction_group']],on=['seg_id','winter'],validate='many_to_one')
    calendar=pd.read_csv(calendar_path,dtype={'prediction_group':str},float_precision='round_trip',parse_dates=['date_kst'])
    calendar=calendar.rename(columns={'date_kst':'date'})
    columns=['prediction_group','winter','date','estimated_temp_mean_c','cold_wet_fraction','ice_valid_slots','cold_wet_slots']
    f=f.merge(calendar[columns],on=['prediction_group','winter','date'],how='left',validate='many_to_one',indicator=True)
    assert f._merge.eq('both').all() and len(f)==202320
    f=f.drop(columns='_merge')
    predictors=['air_temperature_mean','relative_humidity_mean','wind_speed_mean']
    targets=['estimated_temp_mean_c','cold_wet_fraction'];rows=[]
    for (sid,winter),part in f.groupby(['seg_id','winter'],sort=True):
        for predictor,target in product(predictors,targets):
            q=part[[predictor,target]].replace([np.inf,-np.inf],np.nan).dropna()
            constant=len(q)<3 or q[predictor].nunique()<2 or q[target].nunique()<2
            for method in ['pearson','spearman']:
                value=q[predictor].corr(q[target],method=method) if not constant else np.nan
                rows.append(dict(seg_id=sid,winter=int(winter),predictor=predictor,target=target,method=method,
                    daily_pairs=len(q),missing_daily_pairs=len(part)-len(q),correlation=value,
                    status='undefined_constant_or_small_sample' if constant else 'descriptive_daily_estimate_association',
                    observed_ice_target=False,independent_days_assumed=False,causal_effect=False))
    result=pd.DataFrame(rows);result.to_csv(O/'segment_daily_associations.csv',index=False,encoding='utf-8-sig')
    f.to_parquet(O/'segment_daily_estimated_conditions.parquet',index=False,compression='zstd')
    agg=result.groupby(['winter','predictor','target','method']).correlation.agg(['count','median','min','max']).reset_index()
    agg.to_csv(O/'association_ranges.csv',index=False,encoding='utf-8-sig')
    dev=pd.read_parquet(development_path)
    assert dev.station.nunique()==9 and not set(dev.station)&{'12410','23402','33411','33402','33406','12213','23411'}
    temp=dev.temperature_both.to_numpy(float);actual=dev.ice.to_numpy(float)
    water=dev[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].to_numpy(float)
    valid=np.isfinite(actual)&np.isfinite(temp)&~np.isnan(water).all(axis=1)
    q=dev.loc[valid,['station','time','ice']].copy()
    wet=(water[:,0]>=temp)|(water[:,1]>0)|(water[:,2]>0)
    q['temperature_bin']=pd.cut(temp[valid],[-np.inf,-2,0,2,np.inf],labels=['<=-2','(-2,0]','(0,2]','>2'],right=True).astype(str)
    q['moisture_proxy']=np.where(wet[valid],'present','not_detected')
    per_site=q.groupby(['station','temperature_bin','moisture_proxy'],observed=True).ice.agg(['size','sum']).reset_index().rename(columns={'size':'valid_pairs','sum':'observed_ice_pairs'})
    per_site['observed_ice_fraction']=per_site.observed_ice_pairs/per_site.valid_pairs
    per_site.to_csv(O/'development_observed_ice_by_condition_site.csv',index=False,encoding='utf-8-sig')
    pooled=per_site.groupby(['temperature_bin','moisture_proxy']).agg(valid_pairs=('valid_pairs','sum'),observed_ice_pairs=('observed_ice_pairs','sum'),
        available_stations=('station','nunique'),equal_station_mean_ice_fraction=('observed_ice_fraction','mean')).reset_index()
    pooled['pooled_observed_ice_fraction']=pooled.observed_ice_pairs/pooled.valid_pairs
    pooled.to_csv(O/'development_observed_ice_by_condition.csv',index=False,encoding='utf-8-sig')
    assert pooled.valid_pairs.sum()==valid.sum() and pooled.observed_ice_pairs.sum()==np.nansum(actual[valid])
    write(O/'summary.json',dict(status='condition_evidence_computed',segment_daily_rows=len(f),association_rows=len(result),
        winter_segment_rows=int(result[['seg_id','winter']].drop_duplicates().shape[0]),development_valid_pairs=int(valid.sum()),
        development_observed_ice_pairs=int(np.nansum(actual[valid])),development_stations=9,
        associations_are_model_estimate_consistency_not_causal_ice_effect=True,observation_bins_are_descriptive_not_selected_thresholds=True,
        observed_ice_conditions=pooled.to_dict('records'),association_ranges=agg.replace({np.nan:None}).to_dict('records')))
    print('CONDITION EVIDENCE',len(f),'daily rows;',len(result),'association rows;',int(valid.sum()),'development pairs',flush=True)

if __name__=='__main__':main()
