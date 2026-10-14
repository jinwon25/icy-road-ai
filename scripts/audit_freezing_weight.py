"""학습 제외·가중치·저장모델·온도/일별 지표·사건·내부 선택을 별도 검산."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import sys
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read, write, preservation
from scripts.audit_qa633_development import reference
from scripts.audit_temperature_blind_validation import compare
from src.data_source import sha256_file as sha
from src.method_blending import domain

OUT = ROOT / 'outputs/private/freezing_weight_20261014_v1'
SOURCE = ROOT / 'outputs/private/weather_memory_controls_20261013_v1'


def temperature(frame, name):
    y, p = frame.road_temp.to_numpy(float), frame[name].to_numpy(float)
    valid = np.isfinite(y) & np.isfinite(p)
    def calculate(mask):
        diff = p[mask] - y[mask]
        return dict(n=int(mask.sum()), mae=float(np.abs(diff).mean()) if len(diff) else None,
                    rmse=float(np.sqrt((diff * diff).mean())) if len(diff) else None,
                    bias=float(diff.mean()) if len(diff) else None)
    stations = {s: calculate(valid & frame.station.eq(s).to_numpy()) for s in sorted(frame.station.unique())}
    return dict(pooled=calculate(valid), stations=stations,
        station_macro={m: float(np.mean([v[m] for v in stations.values() if v['n']])) for m in ['mae', 'rmse', 'bias']},
        near_freezing=calculate(valid & (y >= -2) & (y <= 2)))


def events(frame, name):
    result = {}
    for station, part in frame.groupby('station'):
        part = part.sort_values('time')
        y = part.ice.to_numpy(float)
        p = part['ice_' + name].to_numpy(int)
        t = part.time.to_numpy(dtype='datetime64[ns]')
        start, length, hits = None, 0, 0
        for i in range(len(part)):
            if y[i] == 1:
                if start is None or i == 0 or y[i-1] != 1 or t[i] - t[i-1] != np.timedelta64(10, 'm'):
                    if start is not None:
                        result[(station, str(start))] = (length, hits)
                    start, length, hits = t[i], 0, 0
                length += 1
                hits += int(p[i])
            elif start is not None:
                result[(station, str(start))] = (length, hits)
                start, length, hits = None, 0, 0
        if start is not None:
            result[(station, str(start))] = (length, hits)
    return result


def reconstruct(frame, names, baseline):
    pop = sorted(frame.station.unique())
    result, identity, tp_by_station = {}, {}, {}
    for name in names:
        p = frame[name].to_numpy(float)
        water = frame[['aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']].to_numpy(float)
        missing = ~np.isfinite(p) | np.isnan(water).all(axis=1)
        binary = ((p <= 0) & ((water[:, 0] >= p) | (water[:, 1] > 0) | (water[:, 2] > 0))).astype(np.int8)
        binary[missing] = frame.original.to_numpy(np.int8)[missing]
        if 'ice_' + name in frame:
            np.testing.assert_array_equal(binary, frame['ice_' + name])
        frame['ice_' + name] = binary
        y = frame.ice.to_numpy(float)
        valid = np.isin(y, [0, 1])
        tp_by_station[name] = {s:int((valid & (y == 1) & (binary == 1) & frame.station.eq(s).to_numpy()).sum()) for s in pop}
        result[name] = dict(temperature=temperature(frame, name),
            fp=int((valid & (y == 0) & (binary == 1)).sum()), fn=int((valid & (y == 1) & (binary == 0)).sum()),
            daily={str(n): reference(frame, 'ice_' + name, pop, n)[0] for n in [144, 1]})
        identity[name] = events(frame, name)
    for name in names:
        r, b = result[name], result[baseline]
        e, be = identity[name], identity[baseline]
        assert e.keys() == be.keys() and all(e[k][0] == be[k][0] for k in e)
        lost = sum(be[k][1] > 0 and e[k][1] == 0 for k in e)
        t, bt = r['temperature'], b['temperature']
        good_temp = all(t['station_macro'][m] < bt['station_macro'][m]-1e-12 for m in ['mae', 'rmse'])
        good_temp &= all(t['stations'][s]['mae'] <= bt['stations'][s]['mae']*1.05+1e-12 for s in pop)
        good_temp &= t['near_freezing']['mae'] <= bt['near_freezing']['mae']+1e-12
        good_ice = r['fp'] <= b['fp'] and r['fn'] <= b['fn'] and lost == 0
        good_ice &= all(tp_by_station[name][s] >= tp_by_station[baseline][s] for s in pop)
        good_ice &= all(r['daily'][n][m+'_available_station_mean']+1e-12 >= b['daily'][n][m+'_available_station_mean']
                        for n in ['144', '1'] for m in ['precision', 'recall', 'f1'])
        r.update(temperature_gate=bool(good_temp), ice_gate=bool(good_ice), eligible=bool(good_temp and good_ice), lost_events=lost)
    return result


def main():
    if (OUT / 'independent_verification.json').exists():
        raise FileExistsError('Preserve completed audit')
    frozen = preservation()
    s, plan, groups = (read(OUT / name) for name in ['summary.json', 'experiment_plan.json', 'groups.json'])
    for rel, digest in read(OUT / 'input_signatures.json').items():
        assert sha(ROOT / rel) == digest, rel
    for rel, digest in s['files'].items():
        assert sha(OUT / rel) == digest, rel
    data = domain(pd.read_parquet(ROOT / 'outputs/private/weather_distance_20261010_v1/development_inputs.parquet'))
    receipts = read(OUT / 'fit_receipts.json')
    assert len(receipts) == 20
    checked = 0
    refits = 0
    with threadpool_limits(limits=2):
        for r in receipts:
            excluded = set().union(*(set(groups[g]) for g in r['excluded_groups']))
            train = data.loc[~data.station.isin(excluded) & np.isfinite(data.road_temp) & np.isfinite(data.asos_air_temp)]
            query = data.loc[data.station.isin(excluded)]
            assert r['training_rows'] == len(train) and r['training_stations'] == sorted(train.station.unique())
            assert not excluded.intersection(r['training_stations']) and excluded == set(r['forbidden_stations'])
            assert r['parameters'] == plan['hgb_parameters'] | {'loss': 'squared_error' if 'mse' in r['candidate'] else 'absolute_error'}
            fingerprint = hashlib.sha256(pd.util.hash_pandas_object(train[['station', 'time', 'road_temp', *r['features']]], index=True).to_numpy().tobytes()).hexdigest()
            assert fingerprint == r['training_values_sha256']
            y = train.road_temp.to_numpy(float)
            w = 1 + 4 * np.exp(-0.5 * (y / 2)**2)
            w /= w.mean()
            assert hashlib.sha256(w.tobytes()).hexdigest() == r['weights_sha256']
            path = OUT / r['model_path']
            assert sha(path) == r['model_sha256']
            model = joblib.load(path)
            expected = np.where(np.isfinite(query.asos_air_temp), model.predict(query[r['features']]), np.nan)
            stored = pd.read_parquet(path.parent / 'predictions.parquet')
            pd.testing.assert_frame_equal(stored[['station', 'time']], query[['station', 'time']].reset_index(drop=True))
            np.testing.assert_array_equal(stored[r['candidate']], expected)
            checked += len(query)
            # 첫 이중 제외 맥락의 두 손실을 다시 적합하여 저장 모델 재현도 확인한다.
            if r['excluded_groups'] == ['honam_baekyang', 'seohaean_seocheon']:
                fitted = HistGradientBoostingRegressor(**r['parameters']).fit(train[r['features']], train.road_temp, sample_weight=w)
                np.testing.assert_array_equal(fitted.predict(query[r['features']]), model.predict(query[r['features']]))
                refits += 1
            print('모델 검산', '__'.join(r['excluded_groups']), r['candidate'], flush=True)
    assert refits == 2
    baseline, secondary = plan['baseline'], plan['secondary_baseline']
    names = [baseline, secondary, *plan['candidates']]
    decisions = read(OUT / 'decisions.json')
    reports_checked = 0
    for g in sorted(groups):
        for kind in ['inner_oof', 'outer_predictions']:
            saved = pd.read_parquet(OUT / g / (kind + '.parquet'))
            origin = pd.read_parquet(SOURCE / g / (kind + '.parquet'), columns=['station', 'time', 'road_temp', baseline, secondary])
            pd.testing.assert_frame_equal(saved[origin.columns], origin)
            pair = (saved.freezing_mse300.to_numpy() + saved.freezing_mae300.to_numpy()) / 2
            for name, values in [('freezing_pair', pair), ('blend_half', (saved[baseline].to_numpy()+pair)/2),
                                 ('blend_quarter', .75*saved[baseline].to_numpy()+.25*pair)]:
                np.testing.assert_array_equal(saved[name], values)
            if kind == 'outer_predictions':
                context = pd.read_parquet(OUT / 'contexts' / g / 'predictions.parquet')
                aligned = saved.merge(context, on=['station', 'time'], suffixes=('', '_source'), validate='one_to_one')
                assert len(aligned) == len(saved)
                for name in plan['models']:
                    np.testing.assert_array_equal(aligned[name], aligned[name + '_source'])
        f = domain(pd.read_parquet(OUT / g / 'inner_oof.parquet'))
        assert not set(f.station) & set(groups[g])
        for h in set(groups)-{g}:
            key = '__'.join(sorted([g, h]))
            context = pd.read_parquet(OUT / 'contexts' / key / 'predictions.parquet')
            part = f.loc[f.station.isin(groups[h])].merge(context, on=['station', 'time'], suffixes=('', '_source'), validate='one_to_one')
            for model_name in plan['models']:
                np.testing.assert_array_equal(part[model_name], part[model_name + '_source'])
        reconstructed = reconstruct(f, names, baseline)
        for name in names:
            r, old = reconstructed[name], decisions[g]['scores'][name]
            compare(r['temperature'], old['temperature'])
            for n in ['144', '1']:
                compare(r['daily'][n], old['ice']['daily'][n])
                reports_checked += 1
            assert r['fp'] == old['ice']['fp'] and r['fn'] == old['ice']['fn']
            if name in plan['candidates']:
                assert r['eligible'] == old['eligible'] and r['lost_events'] == old['retention']['lost_events']
        accepted = [name for name in plan['candidates'] if reconstructed[name]['eligible']]
        chosen = min(accepted, key=lambda c: (reconstructed[c]['temperature']['station_macro']['mae'],
                       reconstructed[c]['temperature']['station_macro']['rmse'], c)) if accepted else baseline
        assert chosen == decisions[g]['selected'] and accepted == decisions[g]['eligible']
        outer = pd.read_parquet(OUT / g / 'outer_predictions.parquet')
        assert set(outer.station) == set(groups[g])
        np.testing.assert_array_equal(outer['nested_selected'], outer[chosen])
    f = domain(pd.read_parquet(OUT / 'outer_predictions.parquet'))
    joined = pd.concat([pd.read_parquet(OUT / g / 'outer_predictions.parquet') for g in sorted(groups)], ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    pd.testing.assert_frame_equal(f[joined.columns], joined)
    all_names = names + ['nested_selected']
    reconstruct(f, all_names, baseline)
    days = pd.read_csv(OUT / 'daily_metrics.csv', dtype={'station':str}, parse_dates=['date_kst'], float_precision='round_trip')
    stations = pd.read_csv(OUT / 'station_metrics.csv', dtype={'station':str}, float_precision='round_trip')
    for name in all_names:
        compare(temperature(f, name), s['scores'][name]['temperature'])
        for minimum in [144, 130, 72, 1]:
            expected, st, d = reference(f, 'ice_' + name, sorted(f.station.unique()), minimum)
            compare(expected, s['scores'][name]['ice']['daily'][str(minimum)])
            ds = days.loc[days.method.eq(name) & days.minimum_valid_slots.eq(minimum), d.columns].reset_index(drop=True)
            ss = stations.loc[stations.method.eq(name) & stations.minimum_valid_slots.eq(minimum), st.columns].reset_index(drop=True)
            pd.testing.assert_frame_equal(ds, d, check_exact=False, atol=1e-12, rtol=0)
            pd.testing.assert_frame_equal(ss, st, check_exact=False, atol=1e-12, rtol=0)
            reports_checked += 1
    assert preservation() == frozen
    write(OUT / 'independent_verification.json', dict(status='independent_freezing_weight_audit_passed',
        audited_at_utc=datetime.now(timezone.utc).isoformat(), summary_sha256=sha(OUT / 'summary.json'),
        audit_source_sha256=sha(Path(__file__)), model_replayed_values=checked, refitted_models=refits,
        daily_reports_verified=reports_checked, daily_rows_verified=len(days), station_rows_verified=len(stations),
        nested_selection_groups_verified=4, new_independent_assessment=False, assessment_outcomes_used=False,
        old_frozen_files=frozen[0], reserved_frozen_files=frozen[1]))
    print('독립 검산 통과', checked, reports_checked, flush=True)


if __name__ == '__main__':
    main()
