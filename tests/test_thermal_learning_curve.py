import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits


def test_continued_hgb_matches_fixed_length_refit():
    rng=np.random.default_rng(4);x=rng.normal(size=(1200,4));y=x[:,0]**2-x[:,1]+rng.normal(0,.1,1200)
    x[::17,2]=np.nan
    for loss in ['squared_error','absolute_error']:
        kwargs=dict(loss=loss,max_leaf_nodes=7,min_samples_leaf=30,early_stopping=False,random_state=20261024)
        with threadpool_limits(limits=2):
            continued=HistGradientBoostingRegressor(max_iter=10,**kwargs).fit(x,y)
            continued.set_params(warm_start=True,max_iter=20).fit(x,y)
            direct=HistGradientBoostingRegressor(max_iter=20,**kwargs).fit(x,y)
            np.testing.assert_allclose(continued.predict(x),direct.predict(x),rtol=0,atol=1e-12)
