"""온도 추정과 고정 결빙 판정의 근거를 분리해 내보내는 후보 추론 계약."""
import numpy as np
from threadpoolctl import threadpool_limits
from .submission_runtime import infer as infer_icing_reference,FEATURES
from .thermal_runtime import HISTORY_FEATURES,EXTRA
from .solar_thermal_runtime import temperature_predictors,GEOMETRY


def infer(frame, temperature_models, icing_models, feature_kind, weights=None):
    """온도·결빙 모델을 숨겨 혼합하지 않는다. 이력 부족은 명시하고 미래 보간하지 않는다."""
    x, valid, _ = temperature_predictors(frame, feature_kind)
    if not temperature_models:
        raise ValueError('At least one temperature model required')
    if weights is None:
        weights = np.full(len(temperature_models), 1 / len(temperature_models))
    weights = np.asarray(weights, float)
    if weights.shape != (len(temperature_models),) or not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(), 1., rtol=0, atol=1e-12):
        raise ValueError('Finite, nonnegative temperature weights must sum to one')
    components=[]
    base_history=list(FEATURES)+HISTORY_FEATURES+list(EXTRA)
    solar=[c for c in x if c in GEOMETRY]
    allowed_orders=[list(FEATURES)+list(EXTRA),base_history,[c for c in x if c not in GEOMETRY],list(x),base_history+solar]
    with threadpool_limits(limits=2):
        for model in temperature_models:
            order=list(model.feature_names_in_)
            if order not in allowed_orders or not set(order)<=set(x):
                raise ValueError('Temperature model input order mismatch')
            component=np.asarray(model.predict(x[order]), float)
            if component.shape != (len(x),) or not np.isfinite(component).all():
                raise ValueError('Invalid temperature component')
            components.append(component)
    values=np.stack(components)
    temperature=weights@values
    temperature[~valid.to_numpy()]=np.nan
    result=infer_icing_reference(frame,icing_models)
    result['icing_reference_temperature_c']=result.estimated_road_temp_c
    result['icing_reference_component_spread_c']=result.temperature_component_spread_c
    result['icing_policy']='v2_weather12_temperature_moisture'
    result['estimated_road_temp_c']=temperature
    spread=np.ptp(values,axis=0);spread[~valid.to_numpy()]=np.nan
    result['temperature_component_spread_c']=spread
    result['temperature_model_kind']=feature_kind
    result['temperature_model_count']=len(temperature_models)
    if set(HISTORY_FEATURES)<=set(x):
        history_columns=[c for c in x if c in HISTORY_FEATURES or '_prior_mean_' in c]
        result['weather_history_available_features']=x[history_columns].notna().sum(axis=1)
        result['weather_history_expected_features']=len(history_columns)
        result['weather_history_status']=np.where(x[history_columns].notna().all(axis=1),'complete','partial_or_unavailable')
    else:
        result['weather_history_available_features']=0
        result['weather_history_expected_features']=0
        result['weather_history_status']='not_used'
    return result
