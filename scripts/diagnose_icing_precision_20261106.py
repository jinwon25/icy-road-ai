"""개발 지점에서 오경보의 수분 근거와 관측 온도 상태를 분해한다. 조정·선택 없음."""
from pathlib import Path
import sys,json
from datetime import datetime,timezone
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from scripts.evaluate_objective_icing import verify_preserved


def main():
    out=ROOT/'outputs/private/icing_precision_diagnosis_20261106'
    if out.exists():raise FileExistsError('Preserve previous diagnosis')
    preserved=verify_preserved()
    p=ROOT/'outputs/private/two_winter_models_20261024_v1/runtime_predictions.parquet'
    f=pd.read_parquet(p).sort_values(['station','time']).reset_index(drop=True)
    forbidden={'12410','33411','23402','33402','33406','12213','23411'}
    assert not set(f.station)&forbidden
    known=np.isfinite(f.physical_both)&f.ice.isin([0,1])
    f=f.loc[known].copy()
    dew=f.aws_dewpoint.ge(f.temperature_both)&f.aws_age_minutes.between(0,60,inclusive='right')
    rain=f.rain15_max_3h.gt(0)
    snow=f.asos_snow_cm.gt(0)
    reconstructed=f.temperature_both.le(0)&(dew|rain|snow)
    np.testing.assert_array_equal(reconstructed,f.physical_both.astype(bool))
    f['water_source']=np.array(['없음','이슬점','최근 강수','이슬점+최근 강수','적설','이슬점+적설','최근 강수+적설','이슬점+최근 강수+적설'])[
        dew.astype(int)+2*rain.astype(int)+4*snow.astype(int)]
    f['predicted']=f.physical_both.eq(1)
    f['tp']=f.predicted&f.ice.eq(1)
    f['fp']=f.predicted&f.ice.eq(0)
    f['fn']=~f.predicted&f.ice.eq(1)
    f['actual_surface_above_zero']=f.road_temp.gt(0)
    rows=[]
    for (station,winter,source),q in f.groupby(['station','winter','water_source']):
        a=q.loc[q.predicted]
        rows.append(dict(station=station,winter=int(winter),water_source=source,rows=len(q),
            observed_ice=int(q.ice.sum()),alerts=len(a),tp=int(q.tp.sum()),fp=int(q.fp.sum()),fn=int(q.fn.sum()),
            fp_actual_surface_above_zero=int((q.fp&q.actual_surface_above_zero).sum()),
            fp_actual_surface_at_or_below_zero=int((q.fp&q.road_temp.le(0)).sum())))
    out.mkdir()
    table=pd.DataFrame(rows)
    table.to_csv(out/'water_sources.csv',index=False,encoding='utf-8-sig')
    positive=f.loc[f.predicted].copy()
    summary=dict(status='development_false_alarm_diagnosis_complete',at_utc=datetime.now(timezone.utc).isoformat(),
        input_sha256=sha(p),stations=sorted(f.station.unique()),rows=len(f),observed_ice_rows=int(f.ice.sum()),
        alerts=int(f.predicted.sum()),tp=int(f.tp.sum()),fp=int(f.fp.sum()),fn=int(f.fn.sum()),
        false_alarm_surface_above_zero=int((f.fp&f.actual_surface_above_zero).sum()),
        false_alarm_surface_at_or_below_zero=int((f.fp&f.road_temp.le(0)).sum()),
        false_alarm_surface_missing=int((f.fp&f.road_temp.isna()).sum()),
        by_water_source=table.groupby('water_source')[['alerts','tp','fp','fn','fp_actual_surface_above_zero','fp_actual_surface_at_or_below_zero']].sum().reset_index().to_dict('records'),
        protected_outcomes_used=False,external_four_outcomes_used=False,diagnosis_used_to_retune_active_experiment=False,
        production_model_changed=False,new_independent_assessment=False)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
    assert verify_preserved()==preserved
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
