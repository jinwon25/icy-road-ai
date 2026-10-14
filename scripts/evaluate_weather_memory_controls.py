"""학습 길이·거리·손실·학습행을 고정하고 시간 이력만 제거하는 대조군20개."""
from datetime import datetime, timezone
import hashlib
from itertools import combinations
from pathlib import Path
import shutil
import sys
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.method_blending import domain, temperature_gate
from src.temperature_transfer import regression_report
from src.thermal_ice import fixed_thermal_rule, diagnostic_report
from src.weather_distance_ablation import DISTANCE_FREE_FEATURES
from scripts.evaluate_method_blending import read, write, preservation, training

PRIVATE = ROOT / 'outputs/private'
SOURCE = PRIVATE / 'weather_memory_temperature_20261013_v2'
OUT = PRIVATE / 'weather_memory_controls_20261013_v1'
CONFIG = ROOT / 'config/weather_memory_control_experiment.json'
MODELS = ['nohistory12_mse300', 'nohistory12_mae300']
BLENDS = ['equal_nohistory_pair', 'equal_trio_nohistory']
BASELINE = 'equal_distance_mse_mae300'
MEMORY = ['memory12_mse300', 'memory12_mae300', 'equal_memory_pair', 'equal_trio_memory']
FEATURES = list(DISTANCE_FREE_FEATURES)


def main():
    if OUT.exists(): raise FileExistsError('Preserve control experiment')
    freezes = preservation(); plan = read(CONFIG); audit = read(SOURCE / 'independent_verification.json')
    assert audit['status'] == 'independent_weather_memory_temperature_audit_passed' and audit['summary_sha256'] == sha(SOURCE / 'summary.json')
    for rel, digest in read(SOURCE / 'input_signatures.json').items(): assert sha(ROOT / rel) == digest
    OUT.mkdir(); write(OUT / 'experiment_plan.json', plan | {'started_at_utc': datetime.now(timezone.utc).isoformat()})
    pinned = [CONFIG, Path(__file__), ROOT / 'src/weather_distance_ablation.py', ROOT / 'src/temperature_transfer.py', ROOT / 'src/thermal_ice.py',
              SOURCE / 'summary.json', SOURCE / 'independent_verification.json', SOURCE / 'fit_receipts.json', SOURCE / 'groups.json',
              PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet']
    groups = read(SOURCE / 'groups.json'); write(OUT / 'groups.json', groups)
    for g in groups:
        pinned.extend(SOURCE / g / (kind+'.parquet') for kind in ['inner_oof', 'outer_predictions'])
    pinned.append(SOURCE / 'ice_predictions.parquet'); signatures = {str(p.relative_to(ROOT)): sha(p) for p in pinned}
    write(OUT / 'input_signatures.json', signatures); shutil.copy2(Path(__file__), OUT / 'analysis_source.py')
    data = domain(pd.read_parquet(PRIVATE / 'weather_distance_20261010_v1/development_inputs.parquet'))
    old_receipts = read(SOURCE / 'fit_receipts.json'); receipts, predictions = [], {}
    with threadpool_limits(limits=2):
        for excluded in [(g,) for g in sorted(groups)] + list(combinations(sorted(groups), 2)):
            forbidden = set().union(*(set(groups[g]) for g in excluded)); train = training(data, forbidden); query = data.loc[data.station.isin(forbidden)]
            folder = OUT / 'contexts' / '__'.join(excluded); folder.mkdir(parents=True)
            result = query[['station', 'time']].copy()
            for name, memory_name, loss in zip(MODELS, MEMORY, ['squared_error', 'absolute_error']):
                params = plan['hgb_parameters'] | {'loss': loss}
                paired = next(r for r in old_receipts if r['candidate'] == memory_name and r['excluded_groups'] == list(excluded))
                assert paired['parameters'] == params and paired['training_rows'] == len(train) and paired['training_stations'] == sorted(train.station.unique())
                assert paired['features'][:12] == FEATURES and len(paired['features']) == 42
                started = time.monotonic(); model = HistGradientBoostingRegressor(**params).fit(train[FEATURES], train.road_temp)
                path = folder / (name+'.joblib'); joblib.dump(model, path, compress=3)
                result[name] = np.where(np.isfinite(query.asos_air_temp), model.predict(query[FEATURES]), np.nan)
                receipts.append(dict(candidate=name, paired_memory_candidate=memory_name, excluded_groups=list(excluded), forbidden_stations=sorted(forbidden),
                     training_stations=sorted(train.station.unique()), training_rows=len(train), features=FEATURES, parameters=params,
                     training_values_sha256=hashlib.sha256(pd.util.hash_pandas_object(train[['station', 'time', 'road_temp', *FEATURES]], index=True).to_numpy().tobytes()).hexdigest(),
                     model_path=path.relative_to(OUT).as_posix(), model_sha256=sha(path), fit_seconds=time.monotonic()-started))
                print('대조군 학습:', '__'.join(excluded), name, round(receipts[-1]['fit_seconds'], 2), flush=True)
            result.to_parquet(folder / 'predictions.parquet', index=False, compression='zstd'); predictions[excluded] = result
    write(OUT / 'fit_receipts.json', receipts); parts, decisions = [], {}
    for g in groups:
        folder = OUT / g; folder.mkdir(); frames = {}
        for kind in ['inner_oof', 'outer_predictions']:
            reference = pd.read_parquet(SOURCE / g / (kind+'.parquet'), columns=['station', 'time', 'group', 'road_temp', BASELINE, *MEMORY])
            query_parts = []
            for h in sorted(set(groups)-{g}) if kind == 'inner_oof' else [g]:
                excluded = tuple(sorted([g, h])) if kind == 'inner_oof' else (g,)
                query_parts.append(predictions[excluded].loc[predictions[excluded].station.isin(groups[h])])
            frame = reference.merge(pd.concat(query_parts), on=['station', 'time'], how='left', validate='one_to_one')
            pd.testing.assert_frame_equal(frame[reference.columns], reference)
            assert all(np.array_equal(np.isfinite(frame[c]), np.isfinite(frame[BASELINE])) for c in MODELS)
            frame[BLENDS[0]] = (frame[MODELS[0]]+frame[MODELS[1]])/2; frame[BLENDS[1]] = (frame[BASELINE]+frame[BLENDS[0]])/2
            frames[kind] = frame
        inner, outer = frames['inner_oof'], frames['outer_predictions']
        reports = {c: regression_report(inner, inner[c]) for c in [BASELINE, *MODELS, *BLENDS]}
        eligible = [c for c in [*MODELS, *BLENDS] if temperature_gate(reports[c], reports[BASELINE])]
        chosen = min(eligible, key=lambda c: (reports[c]['station_macro']['mae'], reports[c]['station_macro']['rmse'], c)) if eligible else BASELINE
        decisions[g] = dict(selected_candidate=chosen, inner_reports=reports, outer_labels_used=False, selection_groups=sorted(set(groups)-{g}))
        outer['selected_control'] = outer[chosen]; outer['selected_candidate'] = chosen
        inner.to_parquet(folder / 'inner_oof.parquet', index=False, compression='zstd'); outer.to_parquet(folder / 'outer_predictions.parquet', index=False, compression='zstd'); parts.append(outer)
    write(OUT / 'decisions.json', decisions)
    combined = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    metrics = {c: regression_report(combined, combined[c]) for c in [BASELINE, *MEMORY, *MODELS, *BLENDS, 'selected_control']}
    labels = pd.read_parquet(SOURCE / 'ice_predictions.parquet', columns=['station', 'time', 'ice', 'baseline_prediction'])
    classified = combined.merge(labels, on=['station', 'time'], validate='one_to_one')
    water = combined[['station', 'time']].merge(data[['station', 'time', 'aws_dewpoint', 'rain15_max_3h', 'asos_snow_cm']], on=['station', 'time'], validate='one_to_one')
    ice = {}
    for name in [*MODELS, *BLENDS, 'selected_control']:
        p, fallback, _ = fixed_thermal_rule(classified[name], water, classified.baseline_prediction, True); classified['ice_'+name] = p
        r, stations, days, events = diagnostic_report(classified, p); ice[name] = r | {'fallback_rows': int(fallback.sum())}
        for label, table in [('stations', stations), ('days', days), ('events', events)]: table.to_csv(OUT / f'ice_{label}_{name}.csv', index=False)
    combined.to_parquet(OUT / 'outer_predictions.parquet', index=False, compression='zstd'); classified.to_parquet(OUT / 'ice_predictions.parquet', index=False, compression='zstd')
    assert all(sha(ROOT / rel) == digest for rel, digest in signatures.items()) and preservation() == freezes
    summary = dict(status='same_parameter_memory_controls_complete', completed_at_utc=datetime.now(timezone.utc).isoformat(), metrics=metrics,
         gate_vs_original_trio={c: temperature_gate(metrics[c], metrics[BASELINE]) for c in [*MODELS, *BLENDS, 'selected_control']},
         memory_gate_vs_matched_control={m: temperature_gate(metrics[m], metrics[c]) for m, c in zip(MEMORY, MODELS+BLENDS)},
         choices={g: d['selected_candidate'] for g, d in decisions.items()}, ice_diagnostic=ice, new_model_fits=20,
         assessment_outcomes_used=False, new_independent_assessment=False, model_promoted=False, old_frozen_files=freezes[0], reserved_frozen_files=freezes[1],
         files={p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()})
    write(OUT / 'summary.json', summary); print('완료', summary['gate_vs_original_trio'], summary['memory_gate_vs_matched_control'])


if __name__ == '__main__': main()
