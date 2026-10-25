"""648개 규칙을 별도 pandas 구현으로 다시 계산해 빠른 탐색 집계와 대조한다."""
from itertools import product
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.two_winter import validate
from src.data_source import sha256_file as sha
from scripts.evaluate_method_blending import preservation


def main():
    folder=ROOT/'outputs/private/extended_ice_rules_20261024_v1'
    out=ROOT/'outputs/private/extended_ice_rules_audit_20261024_v1'
    if out.exists():raise FileExistsError('Preserve rule audit')
    summary=json.loads((folder/'summary.json').read_text('utf-8'))
    for name,digest in summary['files'].items():assert sha(folder/name)==digest,name
    plan=json.loads((folder/'plan.json').read_text('utf-8'))['settings'];f=validate(pd.read_parquet(folder/'predictions.parquet'))
    frozen=preservation();stations=sorted(f.station.unique());expected=np.load(folder/'station_scores.npy')
    table=pd.read_csv(folder/'policy_scores.csv',keep_default_na=False);rain=pd.Series(np.nan,index=f.index)
    for _,part in f.groupby('station'):
        result=part.set_index('time').aws_rain_15m.rolling('180min',closed='left',min_periods=15).mean()
        rain.loc[part.index]=result.to_numpy()
    valid=(f[['asos_air_temp','aws_air_temp','aws_humidity','aws_dewpoint']].notna().all(axis=1)&rain.notna()
           &f.asos_age_minutes.between(1,60)&f.aws_age_minutes.between(1,60))
    np.testing.assert_array_equal(valid,f.common_valid)
    pair=valid&f.ice.isin([0,1]);scores=[]
    specs=list(product(plan['sources'],plan['thresholds'],plan['moisture'],plan['consecutive_slots']))
    for index,(source,threshold,moisture,slots) in enumerate(specs):
        cold={'asos':f.asos_air_temp,'aws':f.aws_air_temp,'mean':(f.asos_air_temp+f.aws_air_temp)/2}[source]
        base=moisture.removesuffix('_or_rain3h')
        if base=='none':wet=pd.Series(True,index=f.index)
        elif base.startswith('humidity'):wet=f.aws_humidity.ge(float(base.removeprefix('humidity')))
        else:wet=(f.aws_air_temp-f.aws_dewpoint).le(float(base.removeprefix('dew')))
        if moisture.endswith('_or_rain3h'):wet=wet|rain.gt(0)
        raw=cold.le(threshold)&wet&valid
        prediction=raw.copy()
        if slots>1:
            for _,part in f.groupby('station'):
                all_true=raw.loc[part.index].rolling(slots,min_periods=slots).sum().eq(slots)
                contiguous=part.time.diff(slots-1).eq(pd.Timedelta(minutes=10*(slots-1)))
                prediction.loc[part.index]=all_true&contiguous
        counts=pd.DataFrame({'station':f.station,'date':f.time.dt.normalize(),'winter':f.winter,
            'valid':pair.astype(int),'tp':(pair&f.ice.eq(1)&prediction).astype(int),
            'fp':(pair&f.ice.eq(0)&prediction).astype(int),'fn':(pair&f.ice.eq(1)&~prediction).astype(int)})
        daily=counts.groupby(['station','date','winter'],sort=True).sum().reset_index()
        den=2*daily.tp+daily.fp+daily.fn
        daily['f1']=(2*daily.tp/den).where(daily.valid.ge(144)&den.gt(0))
        actual=[]
        for period in ['all',2024,2025]:
            part=daily if period=='all' else daily.loc[daily.winter.eq(period)]
            actual.append(part.groupby('station').f1.mean().reindex(stations).fillna(0).to_numpy())
        actual=np.stack(actual);np.testing.assert_allclose(actual,expected[index],rtol=0,atol=1e-12)
        for name in ['tp','fp','fn']:assert int(daily[name].sum())==int(table.iloc[index][name]),(index,name)
        scores.append(actual)
        if index%108==0:print('independent rule audit',index,'/',len(specs),flush=True)
    scores=np.stack(scores);decisions=json.loads((folder/'decisions.json').read_text('utf-8'))
    mapping=f[['station','group']].drop_duplicates().set_index('station').group
    for outer,tracks in decisions.items():
        indexes=[i for i,s in enumerate(stations) if mapping[s]!=outer]
        inner=scores[:,:,indexes].mean(axis=2)
        for track,decision in tracks.items():
            objective=inner[:,0] if track=='mean_f1' else inner[:,1:].min(axis=1)
            selected=int(np.argmax(objective))
            assert selected==decision['policy_index']
            assert abs(objective[selected]-decision['selection_f1'])<1e-12
            assert set(decision['selection_stations']).isdisjoint(decision['excluded_stations'])
    assert preservation()==frozen
    out.mkdir();receipt=dict(status='all_rules_and_spatial_selection_independently_verified',rules=len(specs),
        station_period_scores=int(scores.size),count_comparisons=len(specs)*3,selection_decisions=sum(map(len,decisions.values())),
        max_allowed_absolute_error=1e-12,protected_labels_read=False,old_frozen_files=frozen[0],reserved_frozen_files=frozen[1],
        source_summary_sha256=sha(folder/'summary.json'),audit_code_sha256=sha(Path(__file__)))
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n','utf-8');print(receipt,flush=True)

if __name__=='__main__':main()
