"""개발 자료에서 동일 기상 입력의 혼합 정답을 진단한다. 정답 수정·모델 선택에 사용하지 않는다."""
from pathlib import Path
import sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.anchored_icing import linear_features
from src.weather_information import collision_summary
from src.data_source import sha256_file as sha
from scripts.blind_icing_validation import DEFAULT,verify,read,write,now,old_freezes


def main():
    out=ROOT/'outputs/private/weather_information_20261025_v1'
    if out.exists():raise FileExistsError('Preserve completed diagnostic')
    plan=read(ROOT/'config/residual_icing_20261025.json');source=ROOT/plan['source'];verify(DEFAULT)
    f=pd.read_parquet(source);assert len(set(f.station))==23 and set(f.station).isdisjoint(plan['blocked_stations'])
    f=f.loc[f.available&f.ice.isin([0,1])].reset_index(drop=True)
    out.mkdir(parents=True);write(out/'plan.json',dict(at_utc=now(),source_sha256=sha(source),code_sha256=sha(Path(__file__)),module_sha256=sha(ROOT/'src/weather_information.py'),
        purpose='Input equivalence on existing development rows only. Labels are read for a retrospective diagnostic. No label correction, training, tuning, or new-site evaluation.',
        views=['weather15','weather15_age','weather15_station','weather15_station_age']))
    results=[]
    for scope,g in [('all_23',f),('development_9',f.loc[~f.group.eq('competition')])]:
        for view in ['weather15','weather15_age','weather15_station','weather15_station_age']:
            x=linear_features(g)
            if 'station' in view:x['station']=g.station
            if 'age' in view:x['age']=g.asos_age_minutes
            r=collision_summary(x,g.ice.to_numpy());results.append(dict(scope=scope,view=view,**r));print(scope,view,r['mixed_rows'],r['minimum_fp_if_all_observed_positives_retained'],flush=True)
    pd.DataFrame(results).to_csv(out/'input_equivalence.csv',index=False)
    write(out/'summary.json',dict(status='input_equivalence_diagnostic_complete',at_utc=now(),results=results,
        diagnostic_only=True,station_identity_used_as_model_feature=False,new_four_site_outcomes_used=False,
        interpretation='This is not the irreducible error on future data and is not a daily station F1 upper bound. Additional features can split these groups.'))
    verify(DEFAULT);assert old_freezes()==(47,549)


if __name__=='__main__':main()
