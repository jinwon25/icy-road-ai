"""허용 학습 표만으로 두 고정 모델을 다시 적합하여 봉인 예측과 일치하는지 확인한다."""
from collections import Counter,defaultdict
from pathlib import Path
import sys
import warnings
import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.blind_icing_validation import DEFAULT,PRIVATE,read,write,verify,now
from src.anchored_icing import linear_features
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network


def main():
    out=PRIVATE/'blind_icing_refit_20261025_v1'
    if out.exists():raise FileExistsError('Preserve reproducibility run')
    verify(DEFAULT);plan=read(DEFAULT/'plan.json');data=pd.read_parquet(DEFAULT/'training.parquet')
    f=data.loc[data.available&data.ice.isin([0,1])];assert len(set(f.station))==23 and set(f.station).isdisjoint(plan['new_stations'])
    query=pd.read_parquet(DEFAULT/'inputs.parquet');expected=pd.read_parquet(DEFAULT/'predictions.parquet')
    assert not {'ice','road_temp','state_raw'}&set(query)
    keys=list(zip(f.station,f.winter,f.time.dt.date,f.ice));count=Counter(keys);classes=defaultdict(set);dates=defaultdict(set)
    for s,w,d,y in count:classes[(s,w,d)].add(y);dates[(s,w)].add(d)
    weights=np.array([1/(count[k]*len(classes[k[:3]])*len(dates[k[:2]])) for k in keys]);weights/=weights.mean()
    models={'logit_day_anchor1':make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler(),LogisticRegression(**plan['logistic_parameters'])),
            'hgb_day_anchor1':HistGradientBoostingClassifier(**plan['hgb_parameters'])}
    out.mkdir(parents=True);results=[]
    for name,model in models.items():
        kwargs={'logisticregression__sample_weight':weights} if name.startswith('logit') else {'sample_weight':weights}
        with warnings.catch_warnings(),deny_network() as attempts,threadpool_limits(limits=2):
            warnings.simplefilter('error',ConvergenceWarning);model.fit(linear_features(f),f.ice.to_numpy(int),**kwargs)
            score=model.predict_proba(linear_features(query))[:,1]
        assert not attempts
        np.testing.assert_array_equal(score,expected[name+'_score'])
        pred=np.where(query.available,query.asos_air_temp<=np.minimum(0,2*score-1),np.nan)
        np.testing.assert_array_equal(pred,expected[name])
        path=out/(name+'.joblib');joblib.dump(model,path,compress=3)
        results.append(dict(candidate=name,prediction_rows=len(score),maximum_score_difference=float(np.max(np.abs(score-expected[name+'_score']))),
            refit_sha256=sha(path),original_sha256=sha(DEFAULT/(name+'.joblib')),model_bytes_identical=sha(path)==sha(DEFAULT/(name+'.joblib'))))
        print('REFIT MATCH',name,results[-1]['model_bytes_identical'],flush=True)
    verify(DEFAULT)
    write(out/'receipt.json',dict(status='fixed_models_retrained_and_predictions_identical',at_utc=now(),models=results,
        training_rows=len(f),training_sha256=sha(DEFAULT/'training.parquet'),new_outcomes_read=False,
        network_attempts=0,code_sha256=sha(Path(__file__))))


if __name__=='__main__':main()
