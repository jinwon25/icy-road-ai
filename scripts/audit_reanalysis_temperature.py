"""추가 지표면 온도 실험의 저장 추론·학습 분리·오차 집계를 독립 검산한다."""
from pathlib import Path
import gc
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.reanalysis_models import feature_table
from src.solar_memory_search import feature_table as solar_features
from src.data_source import sha256_file as sha
from src.offline_runtime import deny_network
from scripts.fetch_reanalysis_inputs import read, write
from scripts.evaluate_objective_icing import verify_preserved


def metrics(frame, prediction):
    """평가 코드의 regression_report를 호출하지 않고 잔차로 계산한다."""
    y = frame.road_temp.to_numpy(float)
    p = np.asarray(prediction, float)
    if p.shape != y.shape or np.isinf(p).any() or np.isinf(y).any():
        raise ValueError('Aligned finite or missing temperatures required')
    valid = np.isfinite(y) & np.isfinite(p)

    def subset(mask):
        errors = p[mask] - y[mask]
        return dict(n=int(mask.sum()), mae=float(np.mean(np.abs(errors))) if len(errors) else None,
                    rmse=float(np.sqrt(np.dot(errors, errors) / len(errors))) if len(errors) else None,
                    bias=float(np.sum(errors) / len(errors)) if len(errors) else None)

    stations = {str(s): subset(valid & (frame.station.to_numpy() == s)) for s in sorted(frame.station.unique())}
    supported = [r for r in stations.values() if r['n']]
    macro = {m: float(sum(r[m] for r in supported) / len(supported)) if supported else None
             for m in ['mae', 'rmse', 'bias']}
    return dict(pooled=subset(valid), stations=stations, station_macro=macro,
                near_freezing=subset(valid & (y >= -2) & (y <= 2)))


def equal_nested(actual, expected):
    if isinstance(expected, dict):
        assert set(actual) == set(expected)
        return sum(equal_nested(actual[k], expected[k]) for k in expected)
    if expected is None:
        assert actual is None
    else:
        np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=0)
    return 1


def main():
    study = ROOT / 'outputs/private/reanalysis_temperature_20261031_v1'
    target = study / 'independent_verification.json'
    if target.exists():
        raise FileExistsError('Preserve first completed audit')
    plan = read(study / 'plan.json'); settings = plan['settings']; summary = read(study / 'summary.json')
    for name, digest in plan['signatures'].items():
        assert sha(ROOT / name) == digest, name
    for name, digest in summary['files'].items():
        assert sha(study / name) == digest, name
    assert verify_preserved() == plan['preservation']
    f = pd.read_parquet(ROOT / settings['data']).sort_values(['station', 'time']).reset_index(drop=True)
    assert len(set(f.station)) == 23 and not set(f.station) & set(settings['blocked_stations'])
    baseline = pd.read_parquet(ROOT / settings['baseline']).sort_values(['station', 'time']).reset_index(drop=True)
    metric_checks = equal_nested(metrics(baseline, baseline.prediction), summary['baseline'])
    groups = sorted(set(f.group) - {'competition'})
    base = solar_features(f, 'combined_asos_solar')
    replay_values = 0; refits = 0; maximum_error = 0.
    for candidate in settings['candidates']:
        x = feature_table(f, candidate, base)
        folder = study / candidate
        parts = []
        for held in groups:
            record = read(folder / (held + '.json'))
            train = f.loc[f.group.ne(held) & f.road_temp.notna() & f.asos_air_temp.notna()]
            query = f.loc[f.group.eq(held)]
            assert sorted(train.station.unique()) == record['training_stations']
            assert len(train) == record['training_rows']
            assert not set(train.station) & set(query.station)
            assert record['features'] == list(x)
            path = folder / (held + '.joblib'); assert sha(path) == record['model_sha256']
            model = joblib.load(path)
            assert model.get_params() == record['parameters']
            for key, value in settings['model'].items():
                assert model.get_params()[key] == value
            saved = pd.read_parquet(folder / (held + '.parquet'))
            pd.testing.assert_frame_equal(query[saved.columns.drop('prediction')].reset_index(drop=True),
                                          saved.drop(columns='prediction').reset_index(drop=True), check_exact=True)
            with deny_network() as attempts, threadpool_limits(limits=2):
                values = model.predict(x.loc[query.index])
                values = np.where(query.asos_air_temp.notna(), values, np.nan)
                # 사전 지정한 첫 주 후보·지역을 저장 모델과 별도로 처음부터 재학습한다.
                if candidate == settings['primary_candidate'] and held == groups[0]:
                    repeat = HistGradientBoostingRegressor(**settings['model'])
                    repeat.fit(x.loc[train.index], train.road_temp.to_numpy())
                    refit_values = np.where(query.asos_air_temp.notna(), repeat.predict(x.loc[query.index]), np.nan)
                    np.testing.assert_array_equal(values, refit_values)
                    del repeat
                    refits += 1
            assert not attempts
            np.testing.assert_array_equal(values, saved.prediction.to_numpy())
            maximum_error = max(maximum_error, float(np.nanmax(np.abs(values - saved.prediction))))
            replay_values += len(saved); parts.append(saved)
            del model, train, query
            gc.collect()
            print('AUDIT MODEL', candidate, held, flush=True)
        result = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
        saved = pd.read_parquet(folder / 'predictions.parquet')
        pd.testing.assert_frame_equal(result, saved, check_exact=True)
        pd.testing.assert_frame_equal(result[['station', 'time', 'road_temp', 'ice']],
                                      baseline[['station', 'time', 'road_temp', 'ice']], check_exact=True)
        np.testing.assert_array_equal(np.isfinite(result.prediction), np.isfinite(baseline.prediction))
        report = summary['reports'][candidate]; new = metrics(result, result.prediction); old = metrics(baseline, baseline.prediction)
        metric_checks += equal_nested(new, report['regression'])
        seasons = {}; regions = {}
        for year in [2024, 2025]:
            mask = result.winter.eq(year)
            seasons[str(year)] = dict(new=metrics(result.loc[mask], result.loc[mask, 'prediction']),
                                      baseline=metrics(baseline.loc[mask], baseline.loc[mask, 'prediction']))
        for group in groups:
            mask = result.group.eq(group)
            regions[group] = dict(new=metrics(result.loc[mask], result.loc[mask, 'prediction'])['pooled'],
                                  baseline=metrics(baseline.loc[mask], baseline.loc[mask, 'prediction'])['pooled'])
        metric_checks += equal_nested(seasons, report['winters']) + equal_nested(regions, report['regions'])
        g = settings['temperature_gate']
        gates = dict(pooled_improves=new['pooled']['mae'] <= (1-g['pooled_improvement_min'])*old['pooled']['mae'],
            station_macro_improves=new['station_macro']['mae'] < old['station_macro']['mae'],
            each_winter=all(v['new']['pooled']['mae'] <= (1+g['each_winter_max_harm'])*v['baseline']['pooled']['mae'] for v in seasons.values()),
            each_station=all(new['stations'][s]['mae'] <= (1+g['each_station_max_harm'])*old['stations'][s]['mae'] for s in old['stations']),
            cold_noninferior=new['near_freezing']['mae'] <= (1+g['near_freezing_max_harm'])*old['near_freezing']['mae'],
            regional_support=sum(v['new']['mae'] <= v['baseline']['mae'] for v in regions.values()) >= g['minimum_noninferior_regions'])
        assert gates == report['gates'] and all(gates.values()) == report['eligible']
        del x, result, saved, parts
        gc.collect()
    assert verify_preserved() == plan['preservation']
    write(target, dict(status='passed', model_files=len(summary['fits']), replay_values=replay_values,
        maximum_prediction_error=maximum_error, deterministic_refits=refits, metric_checks=metric_checks,
        summary_sha256=sha(study/'summary.json'), audit_script_sha256=sha(Path(__file__)),
        preservation=plan['preservation'], protected_outcomes_read=False, new_four_site_outcomes_read=False))
    print('AUDIT COMPLETE', replay_values, 'predictions', metric_checks, 'metrics', flush=True)


if __name__ == '__main__':
    main()
