"""첫 겨울 개발 정답의 Ice 코드와 실측 온도 조건 간 설명 범위를 점검한다."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,sys
import numpy as np,pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.audit_joint_surface import read,sha,counts
from src.thermal_ice import validate_development
from src.validation import normalize_state


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'outputs/private/state_temperature_diagnostics_20261009_v1');args=parser.parse_args();out=args.output.resolve()
    if not out.is_relative_to((ROOT/'outputs/private').resolve()):parser.error('Private output required')
    if out.exists():raise FileExistsError('Preserve existing diagnostic')
    p=ROOT/'outputs/private';paths={'labels':p/'ice_group_balanced_20261009_v1/development_index.parquet','temperature':p/'weather_fallback_20261009_v1/training_index.parquet','weather':p/'ice_group_balanced_20261009_v1/feature_matrix.parquet'}
    d=validate_development(pd.read_parquet(paths['labels']));t=pd.read_parquet(paths['temperature']);weather=pd.read_parquet(paths['weather'])
    pd.testing.assert_frame_equal(d[['station','time','group']],t[['station','time','group']]);assert len(weather)==len(d)
    np.testing.assert_allclose(d.ice,d.state_raw.map(normalize_state),rtol=0,atol=0,equal_nan=True)
    d['road_temp']=t.road_temp;d['aws_air_temp']=weather.aws_air_temp;d['aws_dewpoint']=weather.aws_dewpoint
    d['rain15_max_3h']=weather.rain15_max_3h;d['asos_snow_cm']=weather.asos_snow_cm
    station_rows=[];state_rows=[];bins=[];diagnostics=[]
    for station,part in d.groupby('station'):
        ice=part[part.ice.eq(1)];known=part.ice.notna();temperature=ice.road_temp.dropna()
        r=dict(station=station,group=part.group.iloc[0],rows=len(part),valid_states=int(known.sum()),ice_rows=len(ice),ice_fraction=float(len(ice)/known.sum()),
               ice_with_temperature=len(temperature),ice_temperature_min=float(temperature.min()) if len(temperature) else None,ice_temperature_median=float(temperature.median()) if len(temperature) else None,ice_temperature_max=float(temperature.max()) if len(temperature) else None)
        for threshold in [0,1,2,5]:r[f'ice_temperature_above_{threshold}']=int(temperature.gt(threshold).sum())
        station_rows.append(r)
        for state,g in part.groupby('state_raw'):state_rows.append(dict(station=station,group=part.group.iloc[0],state_raw=str(state),rows=len(g),fraction=len(g)/len(part)))
        bucket=pd.cut(part.road_temp,[-np.inf,-5,-2,0,2,5,np.inf],right=True)
        for band,g in part[known].groupby(bucket[known],observed=False):bins.append(dict(station=station,temperature_band=str(band),rows=len(g),ice_rows=int(g.ice.eq(1).sum()),ice_fraction=float(g.ice.mean()) if len(g) else None))
        for name,moisture in [('measured_temperature_le0',False),('measured_temperature_le0_and_weather_moisture',True)]:
            valid=known&part.road_temp.notna();pred=part.road_temp.le(0)
            if moisture:
                valid&=part[['aws_dewpoint','rain15_max_3h','asos_snow_cm']].notna().any(axis=1)
                pred&=part.aws_dewpoint.ge(part.road_temp)|part.rain15_max_3h.gt(0)|part.asos_snow_cm.gt(0)
            diagnostics.append(dict(station=station,policy=name,**counts(part.loc[valid,'ice'].to_numpy(),pred[valid].astype(int).to_numpy())))
    out.mkdir(parents=True);pd.DataFrame(station_rows).to_csv(out/'station_state_temperature.csv',index=False,encoding='utf-8-sig');pd.DataFrame(state_rows).to_csv(out/'station_raw_state.csv',index=False);pd.DataFrame(bins).to_csv(out/'temperature_band_state.csv',index=False);pd.DataFrame(diagnostics).to_csv(out/'measured_condition_diagnostics.csv',index=False)
    result=dict(status='completed_development_diagnostic',created_at_utc=datetime.now(timezone.utc).isoformat(),rows=len(d),stations=len(station_rows),
                source_signature={k:dict(path=str(path),sha256=sha(path)) for k,path in paths.items()},
                actual_temperature_used_for_diagnosis_only=True,model_or_threshold_fitted=False,protected_or_opened_future_outcomes_used=False,
                interpretation='Ice codes at measured temperature above zero do not prove erroneous labels: installation, observation footprint, measurement error, processing lag and residual ice are unresolved. Measured-temperature conditions are diagnostics, not inference candidates or a mathematical upper bound.',
                station_summary=station_rows,source_sha256=sha(__file__))
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),'utf-8');print(pd.DataFrame(station_rows).to_string(index=False),flush=True)


if __name__=='__main__':main()
