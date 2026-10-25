"""고정 예측의 제출용 표. 보호 정답을 받거나 모델·임계값을 선택하지 않는다."""
import numpy as np
import pandas as pd

from src.method_blending import domain
from src.qa633_metrics import daily_table, aggregate
from src.validation import canonical_station_id


def classification_tables(frame, methods, population, thresholds=(144, 130, 72, 1)):
    """지표마다 실제 분모를 보존한다. 관측 결측과 예측 결측은 합치지 않는다."""
    f = frame.copy()
    f['station'] = f.station.map(canonical_station_id)
    domain(f)
    days, stations, summaries = [], [], []
    for method in methods:
        # 기존 기준선 표의 NaN 입력→0 정책을 재해석하지 않고 그대로 내보낸다.
        for minimum in thresholds:
            d = daily_table(f, f[method], population, minimum)
            summary, st = aggregate(d, population)
            for metric in ('precision', 'recall', 'f1'):
                st[metric] = pd.to_numeric(st[metric], errors='raise').astype(float)
            for table in (d, st):
                table.insert(0, 'min_valid_slots', minimum)
                table.insert(0, 'method', method)
                table['official_score'] = False
            days.append(d)
            stations.append(st)
            summaries.append(dict(method=method, min_valid_slots=minimum, **summary))
    return pd.concat(days, ignore_index=True), pd.concat(stations, ignore_index=True), pd.DataFrame(summaries)


def temperature_table(frame, column='equal_nohistory_pair'):
    f = frame.copy()
    f['station'] = f.station.map(canonical_station_id)
    domain(f)
    rows = []
    for station, part in f.groupby('station', sort=True):
        actual, predicted = part.road_temp.to_numpy(float), part[column].to_numpy(float)
        ok = np.isfinite(actual) & np.isfinite(predicted)
        error = predicted[ok] - actual[ok]
        rows.append(dict(station=station, planned_rows=len(part), valid_pairs=int(ok.sum()),
                         missing_pairs=int((~ok).sum()), bias_c=error.mean() if len(error) else np.nan,
                         mae_c=np.abs(error).mean() if len(error) else np.nan,
                         rmse_c=np.sqrt(np.mean(error**2)) if len(error) else np.nan))
    return pd.DataFrame(rows)


def daily_prediction_table(frame):
    """10분 예측의 KST 일별 집계. 결측을 0시간으로 변환하지 않는다."""
    f = frame.copy()
    f['time'] = pd.to_datetime(f.time, errors='raise')
    if f.empty or f.time.isna().any() or f.time.dt.tz is not None:
        raise ValueError('Nonempty naive KST prediction times required')
    if f.duplicated('time').any() or (f.time.dt.minute % 10 != 0).any() or (f.time != f.time.dt.floor('10min')).any():
        raise ValueError('Unique exact ten-minute grid required')
    if not (f.predicted_ice.isna() | f.predicted_ice.isin([0, 1])).all():
        raise ValueError('Only binary-or-missing predictions allowed')
    f['date_kst'] = f.time.dt.normalize()
    f['temperature_valid'] = np.isfinite(f.estimated_road_temp_c.to_numpy(float))
    f['ice_valid'] = f.predicted_ice.notna()
    f['positive'] = f.predicted_ice.eq(1)
    out = f.groupby('date_kst', sort=True).agg(
        present_slots=('time', 'size'), temperature_valid_slots=('temperature_valid', 'sum'),
        ice_valid_slots=('ice_valid', 'sum'), cold_wet_slots=('positive', 'sum'),
        estimated_temp_mean_c=('estimated_road_temp_c', 'mean'),
        estimated_temp_min_c=('estimated_road_temp_c', 'min'),
        estimated_temp_max_c=('estimated_road_temp_c', 'max')).reset_index()
    out['expected_slots'] = 144
    out['missing_ice_slots'] = 144-out.ice_valid_slots
    if out.present_slots.gt(144).any():
        raise ValueError('More than 144 daily slots')
    out['cold_wet_fraction'] = out.cold_wet_slots / out.ice_valid_slots.where(out.ice_valid_slots.gt(0))
    out['cold_wet_hours'] = (out.cold_wet_slots / 6).where(out.ice_valid_slots.gt(0))
    out['complete_day'] = out.ice_valid_slots.eq(144)
    return out


def segment_correlations(frame):
    """구간 연관성의 기술통계. 공유 기상 그룹 수와 결측 쌍을 함께 표시한다."""
    keys = ['scale_m', 'winter', 'seg_id']
    if frame.empty or frame.duplicated(keys).any():
        raise ValueError('Unique segment/scale/winter rows required')
    predictors = ['bridge_code_fraction', 'tunnel_code_fraction', 'point_lat', 'point_lon',
                  'asos_distance_km', 'aws_distance_km_max']
    targets = ['cold_wet_fraction', 'estimated_temp_mean_c']
    rows = []
    for (scale, winter), part in frame.groupby(['scale_m', 'winter'], sort=True):
        for x in predictors:
            for y in targets:
                pairs = part.loc[np.isfinite(part[x]) & np.isfinite(part[y]), [x, y, 'prediction_group']]
                constant = len(pairs) < 3 or pairs[x].nunique() < 2 or pairs[y].nunique() < 2
                for method in ('pearson', 'spearman'):
                    value = pairs[x].corr(pairs[y], method=method) if not constant else np.nan
                    rows.append(dict(scale_m=scale, winter=winter, predictor=x, target=y, method=method,
                        segment_pairs=len(pairs), missing_pairs=len(part)-len(pairs),
                        unique_weather_groups=pairs.prediction_group.nunique(), correlation=value,
                        status='undefined_constant_or_small_sample' if constant else 'descriptive_only',
                        independent_samples=False, causal_effect=False, verified_ice_probability=False))
    return pd.DataFrame(rows)


def two_winter_tables(frame):
    """확장 개발본의 현재 물리 판정과 비교 방법. 첫 겨울 표와 혼합하지 않는다."""
    from src.two_winter import validate
    from src.runtime_metrics import runtime_daily as daily
    from src.temperature_transfer import regression_report
    f=validate(frame.copy())
    methods={'current':f.physical_both,'previous_first_winter':f.physical_first,
             'asos_air_temp_le_zero':f.pred_asos,'learned_nested_selected':f.pred_selected,
             'always_one':np.ones(len(f),int),'always_zero':np.zeros(len(f),int)}
    dayparts=[];stationparts=[];summaries=[]
    for method,prediction in methods.items():
        for minimum in [144,130,72,1]:
            report,stations,days=daily(f,prediction,minimum)
            for metric in ['precision','recall','f1']:stations[metric]=pd.to_numeric(stations[metric]).astype(float)
            for table in [stations,days]:
                table.insert(0,'min_valid_slots',minimum);table.insert(0,'method',method);table['official_score']=False
            dayparts.append(days);stationparts.append(stations)
            summaries.append(dict(method=method,min_valid_slots=minimum,**report))
    report=regression_report(f,f.temperature_both)
    temperatures=[]
    for station,metrics in report['stations'].items():
        planned=int(f.station.eq(station).sum())
        temperatures.append(dict(station=station,planned_rows=planned,valid_pairs=metrics['n'],missing_pairs=planned-metrics['n'],
            bias_c=metrics['bias'],mae_c=metrics['mae'],rmse_c=metrics['rmse']))
    return pd.concat(dayparts,ignore_index=True),pd.concat(stationparts,ignore_index=True),pd.DataFrame(summaries),pd.DataFrame(temperatures)
