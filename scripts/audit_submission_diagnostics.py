"""오류 분해와 날짜 블록 민감도를 저장 원자료에서 별도 계산한다."""
from pathlib import Path
from datetime import datetime, timezone
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read, write, preservation
from scripts.audit_qa633_development import reference
from src.data_source import sha256_file as sha

OUT = ROOT / 'outputs/private/submission_diagnostics_20261014_v1'
PRIVATE = ROOT / 'outputs/private'


def main():
    if (OUT / 'independent_verification.json').exists():
        raise FileExistsError('Preserve diagnostic audit')
    frozen = preservation()
    for rel, digest in read(OUT / 'input_signatures.json').items():
        assert sha(ROOT / rel) == digest
    summary = read(OUT / 'summary.json')
    for rel, digest in summary['files'].items():
        assert sha(OUT / rel) == digest
    f = pd.read_parquet(PRIVATE / 'weather_memory_controls_20261013_v1/ice_predictions.parquet',
        columns=['station','time','road_temp','ice','equal_distance_mse_mae300','equal_nohistory_pair'])
    f = f.merge(pd.read_parquet(PRIVATE / 'thermal_consensus_20261013_v1/predictions.parquet',
        columns=['station','time','original_trio','current_pair']), on=['station','time'], validate='one_to_one')
    f = f.merge(pd.read_parquet(PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet',
        columns=['station','time','aws_dewpoint','rain15_max_3h','asos_snow_cm']), on=['station','time'], validate='one_to_one')
    f['day'] = f.time.dt.normalize()
    pop = sorted(f.station.unique())
    assert len(pop) == 9 and len(f) == 155257
    station = pd.read_csv(OUT / 'station_performance.csv', dtype={'station':str}, float_precision='round_trip')
    numerators, denominators, day_values = [], [], []
    for model, t, p in [('trio','equal_distance_mse_mae300','original_trio'), ('pair','equal_nohistory_pair','current_pair')]:
        _, st, days = reference(f, p, pop, 144)
        saved = pd.read_csv(OUT / (model+'_daily.csv'), dtype={'station':str}, parse_dates=['date_kst'], float_precision='round_trip')
        pd.testing.assert_frame_equal(saved[days.columns], days, check_exact=False, atol=1e-12, rtol=0)
        a, b = [], []
        for s in pop:
            sub = f.loc[f.station.eq(s)]
            valid = np.isfinite(sub.road_temp) & np.isfinite(sub[t])
            error = (sub[t] - sub.road_temp).abs().where(valid)
            grouped = pd.DataFrame({'day':sub.day,'error':error}).groupby('day').error.agg(['sum','count']).reindex(pd.date_range('2024-11-01', periods=120), fill_value=0)
            a.append(grouped['sum'].to_numpy()); b.append(grouped['count'].to_numpy())
            row = station.loc[station.station.eq(s) & station.method.eq(model)].iloc[0]
            assert abs(row.mae-error.mean()) < 1e-12 and row.n == valid.sum()
        numerators.append(a); denominators.append(b)
        day_values.append(days.f1.to_numpy().reshape(9,120))
    a, b, daily = np.asarray(numerators), np.asarray(denominators), np.asarray(day_values)
    repeats = 0
    for block in [3,7,14]:
        indices = np.load(OUT / f'block_{block}_indices.npy')
        assert indices.shape == (2000,120)
        for start in range(0,120,block):
            assert (np.diff(indices[:,start:min(start+block,120)], axis=1) % 120 == 1).all()
        deltas = {'mae':[], 'daily_f1':[]}
        for ids in indices:
            means = a[:,:,ids].sum(axis=2)/b[:,:,ids].sum(axis=2)
            deltas['mae'].append(float(means[1].mean()-means[0].mean()))
            sample = daily[:,:,ids]
            valid = np.isfinite(sample)
            counts = valid.sum(axis=2)
            if (counts > 0).all():
                d = np.nansum(sample,axis=2)/counts
                deltas['daily_f1'].append(float(d[1].mean()-d[0].mean()))
            repeats += 1
        for metric, delta in deltas.items():
            saved = next(r for r in summary['resampling'] if r['metric']==metric and r['block_days']==block)
            np.testing.assert_allclose(np.quantile(delta,[.025,.5,.975]), [saved['lower'],saved['median'],saved['upper']], atol=1e-12,rtol=0)
            assert len(delta) == saved['retained_repetitions']
    error = summary['breakdown']
    fp = f.loc[f.ice.eq(0) & f.current_pair.eq(1)]
    fn = f.loc[f.ice.eq(1) & f.current_pair.eq(0)]
    assert len(fp)==error['fp']==20255 and len(fn)==error['fn']==4952
    assert int(fp.road_temp.le(0).sum())==error['false_positive_observed_at_or_below_zero']==19174
    assert int(fp.road_temp.gt(0).sum())==error['false_positive_observed_above_zero']==1081
    assert int(fn.equal_nohistory_pair.gt(0).sum())==error['false_negative_estimated_above_zero']==2280
    wet = (fn.aws_dewpoint>=fn.equal_nohistory_pair)|(fn.rain15_max_3h>0)|(fn.asos_snow_cm>0)
    assert int((fn.equal_nohistory_pair.le(0)&~wet).sum())==error['false_negative_cold_without_moisture']==2672
    assert preservation()==frozen
    write(OUT / 'independent_verification.json', dict(status='independent_submission_diagnostics_passed',
        completed_at_utc=datetime.now(timezone.utc).isoformat(), summary_sha256=sha(OUT / 'summary.json'),
        audit_source_sha256=sha(Path(__file__)), resamples_verified=repeats,
        station_rows_verified=18, daily_rows_verified=2160, new_model_fits=0, assessment_outcomes_used=False))
    print('진단 검산 통과', repeats)


if __name__ == '__main__':
    main()
