"""감쇠식의 해석해·지점/시각 차단과 저장된 20모형의 점수를 독립 대조한다."""
from pathlib import Path
import json,sys
import numpy as np,pandas as pd,joblib
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.short_forcing_icing_20261106 import features,TAUS
from src.icing_precision_20261106 import WEATHER
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/short_forcing_icing_20261106'
def main():
    assert not (W/'audit.json').exists()
    f=pd.DataFrame({k:np.zeros(200) for k in WEATHER});f['station']='A';f['time']=pd.date_range('2024-11-01',periods=200,freq='10min')
    f['asos_air_temp']=-2.;f['asos_ground_temp']=-3.;f['asos_dewpoint_obs']=-1.
    x=features(f);errors=[]
    for tau in TAUS:
        index=np.arange(200);valid=index*10>=3*tau
        expected=(tau/60)*2*(1-np.exp(-index*10/tau))
        a=x.loc[valid,f'air_cold_past_tau{tau}m'].to_numpy()
        np.testing.assert_allclose(a,expected[valid],rtol=0,atol=5.1e-9);errors.append(float(np.max(np.abs(a-expected[valid]))))
    gap=f.drop(index=100).reset_index(drop=True);g=features(gap)
    for tau in TAUS:
        cut=(gap.time>f.time.iloc[100])&(gap.time<f.time.iloc[101]+pd.Timedelta(minutes=3*tau))
        assert g.loc[cut,f'air_cold_past_tau{tau}m'].isna().all()
    other=f.copy();other['station']='B';other['asos_air_temp']=40
    together=features(pd.concat([f,other],ignore_index=True))
    pd.testing.assert_frame_equal(together.iloc[:200].reset_index(drop=True),x,check_exact=True)
    source=pd.read_parquet(ROOT/'outputs/private/blind_icing_20261025_v2/training.parquet',columns=['station','time','group'])
    fx=pd.read_parquet(W/'features.parquet');records=[]
    for path in sorted(W.glob('*__short_*.json')):
        r=json.loads(path.read_text('utf8'));stem=path.stem;mp=W/(stem+'.joblib');sp=W/(stem+'.parquet')
        assert sha(mp)==r['model_sha256'] and sha(sp)==r['scores_sha256']
        query=source.group.isin(r['excluded']);q=source.loc[query]
        assert not set(q.station)&set(r['training_stations'])
        with threadpool_limits(limits=2):score=joblib.load(mp).predict_proba(fx.loc[query])[:,1]
        saved=pd.read_parquet(sp)
        pd.testing.assert_frame_equal(q[['station','time']].reset_index(drop=True),saved[['station','time']])
        np.testing.assert_array_equal(score,saved.score)
        records.append(dict(name=stem,score_rows=len(saved),reloaded_exact=True,training_held_stations_disjoint=True))
    assert len(records)==20
    result=dict(status='short_forcing_formula_and_saved_scores_verified',constant_cold_closed_form_max_error=max(errors),
        missing_time_gap_resets=True,station_isolation_exact=True,models_reloaded=records,
        protected_outcomes_used=False,production_model_changed=False)
    (W/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print('PASS analytical decay, gaps, station isolation and all 20 reloaded models',flush=True)
if __name__=='__main__':main()
