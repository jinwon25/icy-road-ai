"""서로 다른 후보 조합에 반복된 실제 입력 시계열을 제거하고 기상 노출 기준을 다시 집계한다."""
from pathlib import Path
from datetime import datetime,timezone
from itertools import product
import hashlib,json,sys,shutil
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.seal_protected_weather_20261106 import W,write
from src.inspection_sensitivity import inspection_scenario
from src.risk_review_20261106 import review_matrix
from src.data_source import sha256_file as sha
B=W/'icy_road_model';O=W/'information_group_correction'
FIELDS=['asos_air_temp','aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m','aws_dewpoint',
    'aws_age_minutes','asos_age_minutes','hour_sin','hour_cos','season_sin','season_cos','rain15_max_3h','asos_snow_cm']

def main():
    O.mkdir()
    backup=W/'before_information_group_fix';assert not backup.exists()
    shutil.copytree(B,backup,ignore=shutil.ignore_patterns('local_review','__pycache__','*.pyc'))
    original=B/'results/sections/section_review.csv'
    f=pd.read_csv(original,dtype={'seg_id':str,'prediction_group':str},float_precision='round_trip')
    write(O/'plan.json',dict(at_utc=datetime.now(timezone.utc).isoformat(),
        reason='Exact full predictor-series duplicates exist across different fallback-station candidate combinations. Quantiles must count distinct realised predictor series once.',
        predictor_columns=FIELDS,canonicalisation='ordered 10-minute KST calendar, float64 contiguous arrays, canonical NaN; verify full array equality within each SHA-256 group',
        weather_quantile=.75,curve_quantile=.75,inventory_margin_m=250,minimum_availability=.95,
        model_fitting=False,threshold_search=False,protected_outcomes_read=False,
        primary_parameters_retained=True,original_sections_sha256=sha(original)))
    base=ROOT/'outputs/private/submission_candidate_20261106_v14/data/weather_groups'
    writer=None;buffers={};mapping=[];comparisons=0;signatures={}
    try:
        for winter,q in f.groupby('winter'):
            calendar=pd.date_range(f'{winter}-11-01',f'{winter+1}-03-01',freq='10min',inclusive='left')
            for group in sorted(q.prediction_group.unique()):
                path=base/(group+'.parquet')
                z=pd.read_parquet(path,columns=['time']+FIELDS).sort_values('time').reset_index(drop=True)
                assert pd.DatetimeIndex(z.time).equals(calendar)
                x=np.ascontiguousarray(z[FIELDS].to_numpy(dtype=np.float64));x[np.isnan(x)]=np.nan
                fingerprint=hashlib.sha256(x.tobytes()).hexdigest();key=f'{winter}_{fingerprint}'
                if key in buffers:
                    assert np.array_equal(x,buffers[key],equal_nan=True);comparisons+=1
                else:buffers[key]=x
                mapping.append(dict(winter=int(winter),prediction_group=group,weather_information_group=key,rows=len(z),input_sha256=fingerprint))
                z.insert(0,'prediction_group',group);z.insert(1,'winter',int(winter))
                table=pa.Table.from_pandas(z,preserve_index=False)
                if writer is None:writer=pq.ParquetWriter(B/'data/icing_weather_inputs.parquet',table.schema,compression='zstd')
                writer.write_table(table)
                signatures[path.relative_to(ROOT).as_posix()]=sha(path)
    finally:
        if writer:writer.close()
    mapping=pd.DataFrame(mapping)
    mapping.to_csv(B/'data/weather_information_groups.csv',index=False,encoding='utf-8-sig')
    f=f.merge(mapping[['winter','prediction_group','weather_information_group']],on=['winter','prediction_group'],validate='many_to_one')
    source=f.prediction_group.copy();f.prediction_group=f.weather_information_group
    f,settings=review_matrix(f);f.prediction_group=source
    # 결빙·온도 추정값과 유효 분모는 그대로이며 상대 노출 기준의 모집단만 정정한다.
    old=pd.read_csv(backup/'results/sections/section_review.csv',dtype={'seg_id':str},float_precision='round_trip')
    compare=['seg_id','winter','planned_slots','ice_valid_slots','cold_wet_slots','weather_index_100']
    pd.testing.assert_frame_equal(f[compare],old[compare],check_exact=True)
    overlap=pd.read_csv(B/'results/inventory/overlap_sensitivity.csv',dtype={'seg_id':str},float_precision='round_trip')
    temporary=f.copy();temporary.prediction_group=temporary.weather_information_group
    census,criteria=inspection_scenario(temporary,overlap)
    ids=set(census.index[census.selected])
    assert len(ids)==3
    one=f.loc[f.winter.eq(2024)&f.seg_id.isin(ids)].sort_values(['chain_id','estimated_km_lo'])
    clusters=[]
    for chain,part in one.groupby('chain_id',sort=True):
        current=[];end=None
        for index,row in part.iterrows():
            if end is not None and row.estimated_km_lo>end+.12:
                clusters.append(current);current=[]
            current.append(index);end=row.estimated_km_hi if end is None else max(end,row.estimated_km_hi)
        if current:clusters.append(current)
    f['inspection_candidate']=f.seg_id.isin(ids);f['inspection_area_id']=pd.Series([None]*len(f),dtype=object)
    areas=[]
    for number,indexes in enumerate(clusters,1):
        part=one.loc[indexes];selected=set(part.seg_id);both=f.loc[f.seg_id.isin(selected)]
        row=dict(area_id=f'S{number:02d}',route=part.route_nm.iloc[0],direction=part.flow_lbl.iloc[0],
            estimated_km_start=float(part.estimated_km_lo.min()),estimated_km_end=float(part.estimated_km_hi.max()),
            segments=len(part),directional_length_km=float(part.len_m.sum()/1000),bridge_segments=int(part.bridge_code_fraction.gt(0).sum()),
            curve_context_segments=int(part.curve_deg_100m.gt(criteria['curve_threshold_deg_100m']).sum()),
            exposure_pct_2024=float(np.average(both.loc[both.winter.eq(2024),'weather_index_100'],weights=both.loc[both.winter.eq(2024),'len_m'])),
            exposure_pct_2025=float(np.average(both.loc[both.winter.eq(2025),'weather_index_100'],weights=both.loc[both.winter.eq(2025),'len_m'])),
            official_location_verified=False)
        areas.append(row);f.loc[f.seg_id.isin(selected),'inspection_area_id']=row['area_id']
    f.to_csv(original,index=False,encoding='utf-8-sig')
    f.loc[f.winter.eq(2024)&f.inspection_candidate].to_csv(B/'results/sections/inspection_segments.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(areas).to_csv(B/'results/sections/inspection_areas.csv',index=False,encoding='utf-8-sig')
    write(O/'input_sources.json',signatures)
    write(O/'summary.json',dict(status='actual_weather_information_groups_corrected',declared_groups_by_winter={str(y):int(q.prediction_group.nunique()) for y,q in mapping.groupby('winter')},
        actual_information_groups_by_winter={str(y):int(q.weather_information_group.nunique()) for y,q in mapping.groupby('winter')},
        exact_duplicate_array_comparisons=comparisons,source_groups=len(mapping),primary_segments=len(ids),primary_areas=len(areas),
        criteria=criteria,review_settings=settings,areas=areas,models_changed=False,temperature_or_binary_predictions_changed=False,
        input_rows=len(mapping)*17280,input_data_sha256=sha(B/'data/icing_weather_inputs.parquet'),mapping_sha256=sha(B/'data/weather_information_groups.csv')))
    print(json.dumps(dict(information_groups=mapping.groupby('winter').weather_information_group.nunique().to_dict(),segments=len(ids),areas=areas),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
