"""허용 개발9곳의 고정 후보를 조건별·지점별·날짜 블록별로 진단한다."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read, write, preservation
from src.data_source import sha256_file as sha
from src.method_blending import domain
from src.qa633_metrics import daily_table, aggregate
from src.temperature_transfer import regression_report
from src.development_resampling import circular_day_indices, paired_macro_resamples

PRIVATE = ROOT / 'outputs/private'
SOURCE = PRIVATE / 'weather_memory_controls_20261013_v1'
OUT = PRIVATE / 'submission_diagnostics_20261014_v1'
BASE = 'equal_distance_mse_mae300'
PAIR = 'equal_nohistory_pair'


def main():
    if OUT.exists():
        raise FileExistsError('Preserve diagnostic evidence')
    frozen = preservation()
    paths = [SOURCE / 'ice_predictions.parquet', SOURCE / 'groups.json', SOURCE / 'summary.json',
             SOURCE / 'independent_verification.json', PRIVATE / 'thermal_consensus_20261013_v1/predictions.parquet',
             PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet', Path(__file__),
             ROOT / 'src/development_resampling.py']
    signatures = {str(p.relative_to(ROOT)):sha(p) for p in paths}
    assert read(SOURCE / 'independent_verification.json')['summary_sha256'] == sha(SOURCE / 'summary.json')
    f = domain(pd.read_parquet(paths[0], columns=['station', 'time', 'road_temp', BASE, PAIR, 'ice']))
    old = pd.read_parquet(paths[4], columns=['station', 'time', 'original_trio', 'current_pair'])
    weather = domain(pd.read_parquet(paths[5], columns=['station', 'time', 'asos_air_temp', 'aws_air_temp', 'aws_humidity', 'aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']))
    f = f.merge(old, on=['station', 'time'], validate='one_to_one').merge(weather, on=['station', 'time'], validate='one_to_one')
    assert len(f) == 155257 and f.ice.notna().sum() == 155118
    pop = sorted(f.station.unique())
    groups = read(paths[1])
    group_of = {s:g for g, stations in groups.items() for s in stations}
    OUT.mkdir()
    write(OUT / 'input_signatures.json', signatures)
    write(OUT / 'analysis_plan.json', dict(created_at_utc=datetime.now(timezone.utc).isoformat(),
        block_lengths=[3, 7, 14], repetitions=2000, seed=20261014,
        interpretation='고정된 첫 겨울9지점의 날짜 구성 민감도. 학습·선택 불확실성 및 새 지점 일반화의 신뢰구간 아님.',
        shared_date_draws_across_stations=True, circular_boundary=True, cases='기존 pair의 FN/FP가 최대인 지점일; 동률이면 지점·날짜 오름차순'))
    station_records, days_by_method = [], {}
    for name, temp, binary in [('trio', BASE, 'original_trio'), ('pair', PAIR, 'current_pair')]:
        rt = regression_report(f, f[temp])
        days = daily_table(f, f[binary], pop, 144)
        dr, st = aggregate(days, pop)
        days_by_method[name] = days
        days.to_csv(OUT / (name + '_daily.csv'), index=False)
        for _, s in st.iterrows():
            row = s.to_dict() | {'method':name, 'group':group_of[s.station], **rt['stations'][s.station]}
            sub = f.loc[f.station.eq(s.station) & f.ice.notna()]
            row.update(tp=int(((sub.ice == 1) & (sub[binary] == 1)).sum()),
                       fp=int(((sub.ice == 0) & (sub[binary] == 1)).sum()),
                       fn=int(((sub.ice == 1) & (sub[binary] == 0)).sum()))
            station_records.append(row)
    station = pd.DataFrame(station_records)
    station.to_csv(OUT / 'station_performance.csv', index=False)
    # 두 모델과9지점 모두에 동일 날짜를 적용해 동시 한파의 상관을 유지한다.
    ids = pd.MultiIndex.from_product([pop, pd.date_range('2024-11-01', periods=120)], names=['station', 'date'])
    aggregates = {'mae': [[], []], 'daily_f1': [[], []]}
    for name, temp in [('trio', BASE), ('pair', PAIR)]:
        finite = np.isfinite(f.road_temp) & np.isfinite(f[temp])
        ff = f[['station', 'time']].copy()
        ff['date'] = ff.time.dt.normalize()
        ff['error'] = np.where(finite, np.abs(f[temp] - f.road_temp), 0.)
        ff['valid'] = finite.astype(int)
        g = ff.groupby(['station', 'date'])[['error', 'valid']].sum().reindex(ids, fill_value=0)
        aggregates['mae'][0].append(g.error.to_numpy().reshape(len(pop), 120))
        aggregates['mae'][1].append(g.valid.to_numpy().reshape(len(pop), 120))
        d = days_by_method[name].f1.to_numpy().reshape(len(pop), 120)
        aggregates['daily_f1'][0].append(np.nan_to_num(d))
        aggregates['daily_f1'][1].append(np.isfinite(d).astype(int))
    resampling = []
    for block in (3, 7, 14):
        indices = circular_day_indices(120, block, 2000, 20261014 + block)
        np.save(OUT / f'block_{block}_indices.npy', indices)
        for metric, (numerator, denominator) in aggregates.items():
            values, support = paired_macro_resamples(numerator, denominator, indices)
            # 9지점 모두 양 모델에서 정의된 반복만 비교한다. 변화한 분모를 숨기지 않는다.
            common = (support == len(pop)).all(axis=0)
            delta = values[1, common] - values[0, common]
            quantiles = np.quantile(delta, [.025, .5, .975]) if len(delta) else [None]*3
            resampling.append(dict(metric=metric, block_days=block, repetitions=2000,
                retained_repetitions=int(common.sum()), omitted_repetitions=int((~common).sum()),
                lower=quantiles[0], median=quantiles[1], upper=quantiles[2],
                probability_negative=float((delta < 0).mean()) if len(delta) else None,
                confidence_for_new_stations=False))
    write(OUT / 'date_resampling.json', resampling)
    sensitivity = []
    for excluded in sorted(groups):
        take = ~station.group.eq(excluded)
        a = station.loc[take & station.method.eq('trio')]
        b = station.loc[take & station.method.eq('pair')]
        sensitivity.append(dict(excluded_group=excluded, stations=len(a),
            mae_difference=float(b.mae.mean()-a.mae.mean()), f1_difference=float(b.f1.mean()-a.f1.mean())))
    pd.DataFrame(sensitivity).to_csv(OUT / 'leave_one_group_sensitivity.csv', index=False)
    valid = f.ice.isin([0, 1])
    y, p, actual = f.ice, f.current_pair, f.road_temp
    tp, fp, fn = valid & (y == 1) & (p == 1), valid & (y == 0) & (p == 1), valid & (y == 1) & (p == 0)
    temp_available = np.isfinite(actual)
    predicted_cold = f[PAIR] <= 0
    wet = (f.aws_dewpoint >= f[PAIR]) | (f.rain15_max_3h > 0) | (f.asos_snow_cm > 0)
    breakdown = dict(valid_state_rows=int(valid.sum()), positive_rows=int((valid & y.eq(1)).sum()), tp=int(tp.sum()), fp=int(fp.sum()), fn=int(fn.sum()),
        false_positive_observed_above_zero=int((fp & temp_available & actual.gt(0)).sum()),
        false_positive_observed_at_or_below_zero=int((fp & temp_available & actual.le(0)).sum()),
        false_positive_observed_temperature_missing=int((fp & ~temp_available).sum()),
        false_negative_estimated_above_zero=int((fn & f[PAIR].gt(0)).sum()),
        false_negative_cold_without_moisture=int((fn & predicted_cold & ~wet).sum()),
        false_negative_missing_temperature=int((fn & ~np.isfinite(f[PAIR])).sum()),
        ice_observed_above_zero=int((valid & y.eq(1) & temp_available & actual.gt(0)).sum()),
        interpretation='분류 오류와 관측온도·수분 대리변수의 동시 상태. 제설·염분·센서 이상 등의 원인 판정은 아님.')
    assert sum(breakdown[k] for k in ['false_positive_observed_above_zero', 'false_positive_observed_at_or_below_zero', 'false_positive_observed_temperature_missing']) == breakdown['fp']
    assert sum(breakdown[k] for k in ['false_negative_estimated_above_zero', 'false_negative_cold_without_moisture', 'false_negative_missing_temperature']) == breakdown['fn']
    write(OUT / 'error_breakdown.json', breakdown)
    cohorts = []
    conditions = {'observed_road_at_or_below_zero':actual.le(0), 'estimated_road_at_or_below_zero':predicted_cold,
                  'aws_rh_at_least_90':f.aws_humidity.ge(90), 'rain_proxy_positive':f.rain15_max_3h.gt(0),
                  'snow_proxy_positive':f.asos_snow_cm.gt(0), 'estimated_cold_and_wet':predicted_cold & wet}
    for name, condition in conditions.items():
        for station_id in pop:
            take = valid & f.station.eq(station_id) & condition
            n, ice = int(take.sum()), int((take & y.eq(1)).sum())
            cohorts.append(dict(condition=name, station=station_id, n=n, ice=ice, observed_fraction=ice/n if n else None))
    pd.DataFrame(cohorts).to_csv(OUT / 'weather_condition_associations.csv', index=False)
    cases = []
    d = days_by_method['pair']
    for mode in ['fn', 'fp']:
        row = d.sort_values([mode, 'station', 'date_kst'], ascending=[False, True, True]).iloc[0]
        sub = f.loc[f.station.eq(row.station) & f.time.dt.normalize().eq(row.date_kst)].copy()
        sub.to_csv(OUT / f'{mode}_case.csv', index=False)
        cases.append(dict(mode=mode, station=row.station, date=str(row.date_kst.date()),
                          tp=int(row.tp), fp=int(row.fp), fn=int(row.fn), valid_slots=int(row.valid_slots)))
    write(OUT / 'case_selection.json', cases)
    assert all(sha(ROOT / p) == h for p,h in signatures.items()) and preservation() == frozen
    summary = dict(status='submission_failure_modes_complete', completed_at_utc=datetime.now(timezone.utc).isoformat(),
        breakdown=breakdown, resampling=resampling, group_sensitivity=sensitivity, cases=cases,
        repeated_development=True, assessment_outcomes_used=False, new_model_fits=0,
        old_frozen_files=frozen[0], reserved_frozen_files=frozen[1],
        files={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file()})
    write(OUT / 'summary.json', summary)
    print(breakdown, resampling, sensitivity, flush=True)


if __name__ == '__main__':
    main()
