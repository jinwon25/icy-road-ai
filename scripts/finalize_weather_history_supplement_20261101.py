"""완료조회 키 오류로 영수증만 남지 않은 묶음을 재추론·봉인검사 후 확정한다."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,verify_preserved
from src.data_source import sha256_file as sha
from src.road_weather_runtime import INPUT_COLUMNS,predict_weather
from src.weather_history_runtime import predict_weather_history
from src.offline_runtime import deny_network


def main():
    out=ROOT/'outputs/private/weather_history_supplement_20261101_v2'
    old=ROOT/'outputs/private/weather_observation_supplement_20261031_v1'
    study=ROOT/'outputs/private/weather_humidity_stable_20261101_v1'
    summary=read(study/'summary.json');audit=read(study/'independent_verification.json')
    assert summary['primary_success'] and audit['status']=='passed' and audit['summary_sha256']==sha(study/'summary.json')
    if (out/'receipt.json').exists():raise FileExistsError('Preserve completed history supplement')
    snapshot=out/'factory_before_completion_lookup_fix.py';current=ROOT/'scripts/build_weather_history_supplement.py'
    assert snapshot.read_text('utf-8').replace("regional['preservation']","study['preservation']")==current.read_text('utf-8')
    settings=read(out/'settings.json');metadata=read(out/'model/humidity_history_v1/metadata.json')
    assert sha(out/'data/training.parquet')==settings['data_sha256']==metadata['training_data_sha256']
    assert sha(out/'model/humidity_history_v1'/metadata['file'])==metadata['sha256']
    for path in (old/'model').iterdir():assert sha(path)==sha(out/'model/weather_v1'/path.name)
    for path in ['src/data_source.py','src/observation_io.py','src/road_weather_transfer.py','src/road_weather_runtime.py',
        'src/weather_temporal.py','src/weather_history_stable.py','src/weather_history_runtime.py','src/offline_runtime.py',
        'scripts/predict_weather_history.py','scripts/retrain_weather_history.py']:
        assert sha(ROOT/path)==sha(out/path),path
    context=pd.read_csv(out/'data/weather_context_example.csv',dtype={'station':str},float_precision='round_trip')
    expected=pd.read_csv(out/'data/expected_predictions.csv',dtype={'station':str},parse_dates=['time'],float_precision='round_trip')
    with deny_network() as attempts:
        actual=predict_weather_history(context,out/'model/weather_v1',out/'model/humidity_history_v1')
        original=predict_weather(context.assign(time=pd.to_datetime(context.time)),out/'model/weather_v1')
    assert not attempts
    for column in original:
        if column.startswith('estimated_humidity'):continue
        pd.testing.assert_series_equal(actual[column],original[column],check_exact=True)
    actual=actual.loc[actual.time.ge(pd.Timestamp('2024-12-15'))].reset_index(drop=True)
    pd.testing.assert_frame_equal(actual,expected,check_exact=True)
    f=pd.read_parquet(out/'data/training.parquet');assert not set(f.station)&set(settings['blocked_stations'])
    full=f.loc[f.station.isin(context.station.unique()),['station','time',*INPUT_COLUMNS]]
    with deny_network() as attempts:full_result=predict_weather_history(full,out/'model/weather_v1',out/'model/humidity_history_v1')
    assert not attempts
    full_day=full_result.loc[full_result.time.ge(pd.Timestamp('2024-12-15'))&full_result.time.lt(pd.Timestamp('2024-12-16'))].reset_index(drop=True)
    np.testing.assert_array_equal(full_day.estimated_humidity_pct,actual.estimated_humidity_pct)
    assert len(actual)==432 and actual.humidity_history_status.eq('complete_24h').all()
    assert verify_preserved()==summary['preservation']
    write(out/'completion_lookup_fix.json',dict(original_factory_sha256=sha(snapshot),fixed_factory_sha256=sha(current),
        scope='Preservation metadata lookup only; no model, data, input or prediction changed',source=sha(Path(__file__))))
    write(out/'receipt.json',dict(status='weather_history_supplement_built',metadata=metadata,
        base_model_receipt_sha256=sha(old/'receipt.json'),example_input_rows=len(context),example_output_rows=len(actual),
        maximum_extra_context_prediction_difference=0,training_rows=len(f),training_stations=sorted(f.station.unique()),
        production_road_temperature_changed=False,production_icing_changed=False,
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print('HISTORY SUPPLEMENT FINALIZED',len(actual),'rows; extra-context difference exactly zero',flush=True)


if __name__=='__main__':main()
