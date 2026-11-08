"""개발 지역 예측·관측쌍에서 수분 근거와 오경보의 실제 상태를 재집계한다."""
from pathlib import Path
import argparse,json,hashlib,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.evaluation import evaluate

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,default=ROOT/'results/evaluation/development_predictions.parquet')
    ap.add_argument('--output',type=Path,default=ROOT/'local_review/icing_error_analysis')
    args=ap.parse_args()
    if args.output.exists():raise FileExistsError('기존 분석 결과를 보존합니다. 새 출력 경로를 지정하세요.')
    f=pd.read_parquet(args.input).sort_values(['station','time']).reset_index(drop=True)
    if set(f.station.astype(str))&{'12410','33411','23402','33402','33406','12213','23411'}:
        raise ValueError('이 분석은 고정된 개발 지점의 예측쌍 전용입니다.')
    if f.duplicated(['station','time']).any():raise ValueError('지점·시각이 중복됩니다.')
    state=pd.to_numeric(f.state_raw,errors='coerce').astype('Int64')
    normalized=np.where(state.eq(4).fillna(False),1.,
        np.where(state.isin([1,2,3,10,11,12,13,14,15]),0.,np.nan))
    np.testing.assert_array_equal(normalized,f.ice.to_numpy(float))
    p=f.physical_both
    all_states=pd.DataFrame(dict(state=state,tp=f.ice.eq(1)&p.eq(1),fp=f.ice.eq(0)&p.eq(1),
        fn=f.ice.eq(1)&p.eq(0),time=f.time))
    states=all_states.groupby('state',dropna=False).agg(rows=('time','size'),tp=('tp','sum'),fp=('fp','sum'),fn=('fn','sum')).reset_index()
    official,_,_=evaluate(f,p,minimum_valid_slots=1)
    q=f.loc[p.notna()&f.ice.isin([0,1])].copy()
    dew=q.aws_dewpoint.ge(q.temperature_both)&q.aws_age_minutes.between(0,60,inclusive='right')
    rain=q.rain15_max_3h.gt(0);snow=q.asos_snow_cm.gt(0)
    np.testing.assert_array_equal(q.physical_both.astype(bool),q.temperature_both.le(0)&(dew|rain|snow))
    names=np.array(['없음','이슬점','최근 강수','이슬점+최근 강수','적설','이슬점+적설','최근 강수+적설','이슬점+최근 강수+적설'])
    q['water_source']=names[dew.astype(int)+2*rain.astype(int)+4*snow.astype(int)]
    rows=[]
    for (station,winter,source),g in q.groupby(['station','winter','water_source']):
        alert=g.physical_both.eq(1);tp=alert&g.ice.eq(1);fp=alert&g.ice.eq(0);fn=~alert&g.ice.eq(1)
        rows.append(dict(station=station,winter=int(winter),water_source=source,rows=len(g),
            observed_ice=int(g.ice.sum()),alerts=int(alert.sum()),tp=int(tp.sum()),fp=int(fp.sum()),fn=int(fn.sum()),
            fp_actual_surface_above_zero=int((fp&g.road_temp.gt(0)).sum()),
            fp_actual_surface_at_or_below_zero=int((fp&g.road_temp.le(0)).sum())))
    water=pd.DataFrame(rows)
    pred=q.physical_both.eq(1);false=pred&q.ice.eq(0)
    summary=dict(scope='development_9_sites_two_winters_geographic_holdout',rows=len(q),
        stations=sorted(q.station.unique()),observed_ice_rows=int(q.ice.sum()),alerts=int(pred.sum()),
        tp=int((pred&q.ice.eq(1)).sum()),fp=int(false.sum()),fn=int((~pred&q.ice.eq(1)).sum()),
        false_alarm_surface_above_zero=int((false&q.road_temp.gt(0)).sum()),
        false_alarm_surface_at_or_below_zero=int((false&q.road_temp.le(0)).sum()),
        source_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
        precision_date_station=official['precision'],recall_date_station=official['recall'],f1_date_station=official['f1'],
        actual_ice_stations=official['actual_ice_stations'],no_model_fitted=True,
        actual_temperature_and_state_used_for_error_analysis_only=True)
    args.output.mkdir(parents=True)
    states.to_csv(args.output/'surface_states.csv',index=False)
    water.to_csv(args.output/'moisture_evidence.csv',index=False,encoding='utf-8-sig')
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf8')
    print(json.dumps(summary,ensure_ascii=False,allow_nan=False))

if __name__=='__main__':main()
