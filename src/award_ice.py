"""공간 제외 결빙 점수의 일별 F1 선택과 과거 기상 확장."""
import numpy as np
import pandas as pd
from src.method_blending import domain
from src.submission_runtime import FEATURES

EXISTING = ('binary100_control','hgb_long300','hgb_no_distance','hgb_history','hgb_balanced','catboost400','hurdle_non_dry')
NEW = ('weather_history_unweighted','weather_history_station_class')
THRESHOLDS = np.unique(np.r_[0., np.logspace(-6, 0, 61), .5, 1.0000001])
SMOOTHING = (0, 30, 120)


def past_score(frame, score, minutes):
    """현재 점수와 엄격한 과거 평균의 고정 반반 평균. 과거 부족 시 현재 점수."""
    domain(frame)
    score = np.asarray(score, float)
    if score.shape != (len(frame),) or not np.isfinite(score).all() or not ((score >= 0)&(score <= 1)).all():
        raise ValueError('Aligned finite 0..1 score required')
    if minutes not in SMOOTHING:
        raise ValueError('Unplanned smoothing')
    if not minutes:
        return score.copy()
    f = frame[['station','time']].reset_index(drop=True).copy()
    f['score'] = score
    output = score.copy()
    for _, part in f.groupby('station'):
        p = part.sort_values('time')
        series = pd.Series(p.score.to_numpy(), index=pd.DatetimeIndex(p.time))
        prior = series.rolling(f'{minutes}min', closed='left', min_periods=int(np.ceil(.8*minutes/10))).mean().to_numpy()
        output[p.index] = np.where(np.isfinite(prior), .5*(prior+p.score.to_numpy()), p.score)
    return output


def threshold_curve(frame, score, thresholds=THRESHOLDS, minimum=144):
    """히스토그램 누적합으로 모든 임계값의 날짜→지점 F1을 정확히 계산한다."""
    domain(frame)
    s = np.asarray(score, float)
    ts = np.asarray(thresholds, float)
    if s.shape != (len(frame),) or not np.isfinite(s).all() or ts.ndim != 1 or not len(ts) or not np.isfinite(ts).all() or np.any(np.diff(ts) <= 0):
        raise ValueError('Finite aligned score and sorted unique thresholds required')
    valid = frame.ice.isin([0,1]).to_numpy()
    if not (valid | frame.ice.isna().to_numpy()).all():
        raise ValueError('Invalid label')
    pop = sorted(frame.station.unique())
    day, keys = pd.factorize(pd.MultiIndex.from_arrays([frame.station[valid], pd.to_datetime(frame.time[valid]).dt.normalize()]), sort=True)
    ds = np.array([pop.index(k) for k in keys.get_level_values(0)])
    y = frame.ice.to_numpy(float)[valid].astype(int)
    nday, nt = len(keys), len(ts)
    counts = np.bincount(day, minlength=nday)
    positive = np.bincount(day, weights=y, minlength=nday)
    bins = np.searchsorted(ts, s[valid], side='right')
    def cumulative(weights):
        h = np.bincount(day*(nt+1)+bins, weights=weights, minlength=nday*(nt+1)).reshape(nday, nt+1)
        return np.cumsum(h[:, ::-1], axis=1)[:, ::-1][:, 1:]
    tp, fp = cumulative(y), cumulative(1-y)
    fn = positive[:, None]-tp
    denom = 2*tp+fp+fn
    active = (denom > 0)&(counts[:, None] >= minimum)
    daily = np.divide(2*tp, denom, out=np.zeros_like(tp), where=active)
    station_sum = np.zeros((len(pop),nt)); station_days = np.zeros((len(pop),nt))
    np.add.at(station_sum, ds, daily); np.add.at(station_days, ds, active)
    station_f1 = np.divide(station_sum, station_days, out=np.zeros_like(station_sum), where=station_days>0)
    return pd.DataFrame(dict(threshold=ts, f1_fixed_population=station_f1.mean(axis=0),
        f1_defined_stations=(station_days>0).sum(axis=0), f1_days=active.sum(axis=0),
        tp=tp.sum(axis=0).astype(int), fp=fp.sum(axis=0).astype(int), fn=fn.sum(axis=0).astype(int)))


def select_row(table):
    """합산 시점 F1이나 외부 지역 결과로 동률을 풀지 않는다."""
    if table.empty or not np.isfinite(table.f1_fixed_population).all():
        raise ValueError('Nonempty scored table required')
    return table.sort_values(['f1_fixed_population','fp','threshold','candidate','smoothing_minutes'],
                             ascending=[False,True,False,True,True], kind='stable').iloc[0].to_dict()


def history_features(frame):
    """입력은 이미 시각 t보다 앞선 기상이며 추가 이력도 [t-window,t)만 쓴다."""
    domain(frame)
    f = frame.reset_index(drop=True)
    x = f[list(FEATURES)].astype(float).copy()
    x['air_dewpoint_gap'] = x.aws_air_temp-x.aws_dewpoint
    for hours in (6,24):
        for column, aggregation in [('aws_air_temp','mean'),('aws_air_temp','min'),('aws_humidity','mean'),('aws_rain_15m','max')]:
            name = f'{column}_past_{hours}h_{aggregation}'
            x[name] = np.nan
            for _, part in f.groupby('station'):
                p = part.sort_values('time')
                values = pd.Series(p[column].to_numpy(float), index=pd.DatetimeIndex(p.time))
                roll = values.rolling(f'{hours}h', closed='left', min_periods=int(np.ceil(.8*hours*6)))
                x.loc[p.index, name] = getattr(roll, aggregation)().to_numpy()
    if np.isinf(x.to_numpy()).any():
        raise ValueError('Infinite feature')
    return x


def station_class_weights(frame):
    domain(frame)
    if not frame.ice.isin([0,1]).all():
        raise ValueError('Valid training labels required')
    counts = frame.groupby(['station','ice']).ice.transform('size').to_numpy(float)
    classes = frame.groupby('station').ice.transform('nunique').to_numpy(float)
    weight = 1/(counts*classes)
    weight /= weight.mean()
    weight = np.minimum(weight,20.)
    return weight/weight.mean()
