"""공식 시간 기상 원문을 캐시 대조군·결측 시각과 대조한다. 정답은 읽지 않는다."""
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read, write, preservation
from src.data_source import sha256_file as sha

PRIVATE = ROOT / 'outputs/private'
OUT = PRIVATE / 'weather_source_gap_audit_20261016_v1'


def parse_hourly(path, requested_time, stations):
    schema, rows = [], []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            match = re.match(r'#\s*(\d+)\.\s*(\w+)\s*:', line)
            if match:
                schema.append((int(match[1]), match[2]))
        else:
            rows.append(line.split())
    schema.sort()
    assert [i for i, _ in schema] == list(range(1, 47))
    columns = [name for _, name in schema]
    assert len(set(columns)) == 46 and {'TM', 'STN', 'TA', 'SD_TOT'} <= set(columns)
    assert all(len(row) == 46 for row in rows)
    f = pd.DataFrame(rows, columns=columns)
    if f.empty:
        return pd.DataFrame(columns=['station', 'source_time', 'air_temp', 'snow_cm'])
    result = pd.DataFrame({'station': f.STN.astype(str), 'source_time': pd.to_datetime(f.TM, format='%Y%m%d%H%M')})
    result['air_temp'] = pd.to_numeric(f.TA)
    result['snow_cm'] = pd.to_numeric(f.SD_TOT)
    # This hourly endpoint uses -99.0 for missing temperature and -9.0 for snow.
    # A real air temperature of -9 C must remain valid; snow absence is not zero.
    result.loc[result.air_temp.lt(-90), 'air_temp'] = np.nan
    result.loc[result.snow_cm.lt(0), 'snow_cm'] = np.nan
    assert result.source_time.eq(pd.Timestamp(requested_time)).all()
    assert set(result.station) <= set(stations) and not result.station.duplicated().any()
    assert np.isfinite(result[['air_temp', 'snow_cm']].dropna().to_numpy()).all()
    return result


def main():
    if OUT.exists():
        raise FileExistsError('Preserve completed raw weather audit')
    frozen = preservation()
    sources = [PRIVATE / 'asos_original_source_probe_20261016_v1',
               PRIVATE / 'asos_original_source_controls_20261016_v1',
               PRIVATE / 'weather_gap_source_followup_20261016_v1']
    records = []
    signatures = {}
    for folder in sources:
        receipt = read(folder / 'receipt.json')
        signatures[str((folder / 'receipt.json').relative_to(ROOT))] = sha(folder / 'receipt.json')
        for record in receipt.get('requests', [receipt]):
            path = folder / ((record['name']+'.txt') if 'name' in record else 'response.txt')
            assert sha(path) == record['response_sha256'] and record['authentication_stored'] is False
            if record['endpoint'].endswith('kma_sfctm2.php'):
                assert record['http_status'] == 200
                p = record['public_parameters']
                weather = parse_hourly(path, pd.to_datetime(p['tm'], format='%Y%m%d%H%M'), p['stn'].split(':'))
                records.append((record.get('name', 'buan_missing_hour'), weather))
            else:
                assert record['http_status'] == 403
            signatures[str(path.relative_to(ROOT))] = sha(path)
    cache_path = PRIVATE / 'releases/20261007/outputs/private/point_sources/asos.parquet'
    cache = pd.read_parquet(cache_path, columns=['station', 'source_time', 'air_temp', 'snow_cm'])
    signatures[str(cache_path.relative_to(ROOT))] = sha(cache_path)
    comparisons = []
    for name, f in records:
        if name in ['cached_first_hour', 'cached_gap_previous_hour', 'jangsu_missing_hour']:
            paired = f.merge(cache, on=['station', 'source_time'], suffixes=('_api', '_cache'), validate='one_to_one')
            assert len(paired) == 1
            for c in ['air_temp', 'snow_cm']:
                np.testing.assert_allclose(paired[c+'_api'], paired[c+'_cache'], equal_nan=True, atol=0, rtol=0)
            comparisons.append(dict(name=name, air_observation_missing=bool(f.air_temp.isna().all()), matches_cache=True))
    assert len(comparisons) == 3
    assert len(dict(records)['buan_missing_hour']) == 0
    assert dict(records)['jangsu_missing_hour'].air_temp.isna().all()
    previous = pd.concat([f for name, f in records if name in ['winter_start_previous_hour', 'second_winter_previous_hour']], ignore_index=True)
    assert len(previous) == 6 and previous.air_temp.notna().all() and previous.snow_cm.isna().all()
    # Inspect input weather only, never the protected road observations.
    index_path = PRIVATE / 'submission_candidate_20261016_v1/data/point_prediction_index.csv'
    index = pd.read_csv(index_path, dtype={'id': str})
    signatures[str(index_path.relative_to(ROOT))] = sha(index_path)
    checks = []
    aws_features = ['aws_air_temp', 'aws_humidity', 'aws_wind_speed', 'aws_rain_15m', 'aws_dewpoint', 'aws_age_minutes']
    for row in index.loc[index.kind.eq('protected')].itertuples():
        path = index_path.parent / 'weather_groups' / (row.prediction_group+'.parquet')
        f = pd.read_parquet(path, columns=['time', 'asos_air_temp', 'asos_age_minutes', 'asos_snow_cm', *aws_features])
        first = f.loc[f.time.eq(pd.Timestamp(f'{row.winter}-11-01'))]
        assert len(first) == 1 and first[aws_features].isna().all().all()
        assert first[['asos_air_temp', 'asos_age_minutes', 'asos_snow_cm']].isna().all().all()
        checks.append(dict(station=row.id, winter=int(row.winter), original_asos_recoverable=True,
                           aws_features_still_missing=True, original_snow_observation_missing=True))
        signatures[str(path.relative_to(ROOT))] = sha(path)
    candidate = PRIVATE / 'submission_candidate_20261016_v1.zip'
    assert sha(candidate) == '80de76bb5da5c9004dc72f066ac45f0221d96a5fd7cf9982c6ba963072f25989'
    OUT.mkdir()
    previous.to_parquet(OUT / 'pre_winter_asos_weather_only.parquet', index=False)
    write(OUT / 'input_signatures.json', signatures)
    assert preservation() == frozen
    result = dict(status='official_weather_source_gap_audit_passed', checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  official_network_requests=7, asos_responses=6, aws_responses=1,
                  cache_control_and_missing_comparisons=comparisons,
                  buan_missing_hour_has_no_observation_row=True, jangsu_missing_hour_temperature_is_missing=True,
                  available_pre_winter_asos_rows=6, protected_first_slot_checks=checks,
                  aws_api_http_status=403, snow_missing_not_zero=True, road_outcomes_read=False,
                  new_model_fits=0, execution_candidate_changed=False, completion_of_prediction_gaps_qualified=False,
                  old_frozen_files=frozen[0], reserved_frozen_files=frozen[1],
                  weather_only_output_sha256=sha(OUT / 'pre_winter_asos_weather_only.parquet'))
    write(OUT / 'receipt.json', result)
    print(result, flush=True)


if __name__ == '__main__':
    main()
