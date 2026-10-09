"""열·수분 입력의 규제 선형 및 가법 스플라인 비교 모델."""
import warnings
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler

SPLINE_COLUMNS = ["near_road_temp", "surface_dewpoint_gap", "aws_air_temp", "aws_humidity"]
# 분석 전 정한 물리 단위의 매듭. 정답 또는 검증 분포로 매듭 위치를 고르지 않는다.
FIXED_KNOTS = np.array([[-15., -20., -20., 0.], [-5., -5., -5., 40.],
                        [0., 0., 0., 70.], [5., 5., 5., 90.], [15., 20., 20., 100.]])
FORBIDDEN = {"station", "time", "ice", "state_raw", "road_temp", "target_road_temp"}


def make_model(columns, kind, config):
    if set(columns) & FORBIDDEN or len(columns) != len(set(columns)):
        raise ValueError("Target values or duplicate features forbidden")
    impute = lambda: SimpleImputer(strategy="median", keep_empty_features=True)
    if kind == "linear":
        transforms = [("numeric", impute(), columns)]
    elif kind == "spline":
        if not set(SPLINE_COLUMNS) <= set(columns):
            raise ValueError("Missing thermal spline columns")
        smooth = Pipeline([("impute", impute()),
                           ("basis", SplineTransformer(knots=FIXED_KNOTS, degree=2,
                                                       extrapolation="linear", include_bias=False))])
        transforms = [("smooth", smooth, SPLINE_COLUMNS),
                      ("linear", impute(), [c for c in columns if c not in SPLINE_COLUMNS])]
    else:
        raise ValueError("Unknown regularized model")
    transforms.append(("missing", MissingIndicator(features="all", error_on_new=False), columns))
    return Pipeline([("inputs", ColumnTransformer(transforms, remainder="drop")),
                     ("scale", StandardScaler()),
                     ("classifier", LogisticRegression(C=config["C"], solver="lbfgs", penalty="l2",
                                                       class_weight={0: 1., 1: config["positive_weight"]},
                                                       max_iter=config["max_iter"], tol=config["tol"],
                                                       random_state=20260923))])


def fit_converged(model, features, labels):
    # 수렴하지 않은 결과를 정상 학습으로 조용히 통과시키지 않는다.
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        model.fit(features, labels)
    return model
