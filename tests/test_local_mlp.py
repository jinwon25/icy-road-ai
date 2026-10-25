import numpy as np
import pandas as pd
import pytest
from src.local_mlp import LocalMLPRegressor


def test_train_only_statistics_and_serialized_predictions(tmp_path):
    import joblib
    x=pd.DataFrame({'temperature':np.arange(24,dtype=float),'missing':np.nan})
    model=LocalMLPRegressor(epochs=2,width=8,batch_size=8).fit(x,x.temperature*.1)
    assert model.mean_[0]==11.5 and model.mean_[1]==0
    before=model.mean_.copy();query=pd.DataFrame({'temperature':[1e4,np.nan],'missing':[1.,np.nan]})
    prediction=model.predict(query);assert np.isfinite(prediction).all()
    np.testing.assert_array_equal(model.mean_,before)
    path=tmp_path/'model.joblib';joblib.dump(model,path)
    np.testing.assert_array_equal(joblib.load(path).predict(query),prediction)
    with pytest.raises(ValueError):model.predict(query[['missing','temperature']])
