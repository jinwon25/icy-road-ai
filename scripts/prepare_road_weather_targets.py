"""허용 23곳의 세 기상 정답만 별도로 읽고 기존 기상 입력과 정렬한다."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file as sha
from src.observation_io import daily_members
from src.road_weather_transfer import TARGETS, ASOS_FIELDS, allowed_csv, clean_target
from scripts.evaluate_objective_icing import read, write, verify_preserved


def main():
    cfg = ROOT/'config/road_weather_transfer_20261031.json'; plan = read(cfg)
    out = ROOT/plan['input_output']
    if out.exists(): raise FileExistsError('Preserve weather target preparation')
    frozen = verify_preserved(); out.mkdir(parents=True)
    release = ROOT/plan['release']; archive_path = competition_archive(release)
    data_path = ROOT/plan['feature_data']; assert sha(data_path) == plan['feature_sha256']
    allowed = set(plan['competition_stations'] + plan['development_stations'])
    assert not allowed & set(plan['blocked_stations'])
    signatures = {p.relative_to(ROOT).as_posix(): sha(p) for p in
                  [cfg, Path(__file__), ROOT/'src/road_weather_transfer.py', archive_path,
                   data_path, ROOT/plan['asos_data']]}
    write(out/'plan.json', dict(at_utc=datetime.now(timezone.utc).isoformat(), settings=plan,
                                signatures=signatures, preservation=frozen))
    columns = ['관측 지점번호', '관측시각 (KST)', '기온 (C)', '습도 (%)', '1분 풍속 (m/s)']
    parts = []; members = []; omitted = 0
    with zipfile.ZipFile(archive_path) as archive:
        for i, member in enumerate(daily_members(archive, 'RWIS')):
            frame, skipped = allowed_csv(archive, member, plan['competition_stations'], columns)
            frame.columns = ['station', 'time'] + TARGETS
            frame['station'] = frame.station.str.strip()
            frame['time'] = pd.to_datetime(frame.time, errors='raise')
            parts.append(frame); omitted += skipped
            members.append(dict(member=member, selected_rows=len(frame), identifier_only_skipped_rows=skipped,
                                crc=archive.getinfo(member).CRC))
            if (i+1)%40 == 0: print('CSV', i+1, flush=True)
    cache_files = []
    for folder in ['kma_rwis_development_v1', 'kma_rwis_reserved_v1']:
        base = release/'outputs/private/external'/folder
        manifest = read(base/'download_manifest.json')
        signatures[(base/'download_manifest.json').relative_to(ROOT).as_posix()] = sha(base/'download_manifest.json')
        for key, record in sorted(manifest['records'].items()):
            station = key.split('/')[0]
            if station not in plan['development_stations']: continue
            path = base/'ten_minute'/(key+'.parquet')
            assert sha(path) == record['ten_minute_sha256'], str(path)
            frame = pd.read_parquet(path, columns=['station', 'time', 'TA', 'HM', 'WS1'])
            assert len(frame) == record['rows_exact_ten_minute']
            assert set(frame.station.astype(str)) == ({station} if len(frame) else set())
            frame.columns = ['station', 'time'] + TARGETS
            if len(frame): parts.append(frame)
            cache_files.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path), rows=len(frame)))
        print('CACHE', folder, len(cache_files), flush=True)
    raw = pd.concat(parts, ignore_index=True)
    raw['station'] = raw.station.astype(str); raw['time'] = pd.to_datetime(raw.time)
    assert not raw.duplicated(['station', 'time']).any()
    assert set(raw.station) == allowed
    bounds_removed = {}
    for target in TARGETS:
        numeric = pd.to_numeric(raw[target], errors='coerce')
        cleaned = clean_target(raw[target], plan['quality_ranges'][target])
        bounds_removed[target] = int((numeric.notna() & cleaned.isna() & ~numeric.isin([-999,-99.9,-99.2,-99.7])).sum())
        raw[target] = cleaned
    raw['winter'] = np.where(raw.time.dt.month>=11, raw.time.dt.year, raw.time.dt.year-1)
    assert set(raw.winter) == {2024,2025}
    assert (raw.time.dt.minute%10 == 0).all() and (raw.time.dt.second == 0).all()
    raw = raw.sort_values(['station','time']).reset_index(drop=True)
    raw.to_parquet(out/'targets.parquet', index=False, compression='zstd')
    counts = raw.groupby(['station','winter']).agg(rows=('time','size'), **{t:(t,'count') for t in TARGETS}).reset_index()
    counts.to_csv(out/'availability.csv', index=False, encoding='utf-8-sig')
    # 읽을 기상 열을 명시한다. 이 캐시에 있는 노면 정답과 ERA5 값은 읽지 않는다.
    feature_columns = ['station','time','group','winter','asos_air_temp','asos_ground_temp',
        'asos_humidity','asos_rain_mm','asos_snow_cm','asos_cloud_tenths','asos_solar_mj_m2',
        'asos_age_minutes','aws_air_temp','aws_humidity','aws_wind_speed','aws_rain_15m',
        'aws_dewpoint','aws_age_minutes','hour_sin','hour_cos','season_sin','season_cos',
        'asos_distance_km','aws_distance_km','solar_altitude_deg','solar_sine_positive']
    f = pd.read_parquet(data_path, columns=feature_columns)
    assert set(f.station) == allowed and not f.duplicated(['station','time']).any()
    more = ['asos_'+n for n in ASOS_FIELDS if 'asos_'+n not in f]
    asos = pd.read_parquet(ROOT/plan['asos_data'], columns=['station','time']+more)
    assert set(asos.station) == allowed
    f = f.merge(asos, on=['station','time'], how='left', validate='one_to_one', indicator=True)
    assert f._merge.eq('both').all(); f = f.drop(columns='_merge')
    f = f.merge(raw.drop(columns='winter'), on=['station','time'], how='left', validate='one_to_one', indicator=True)
    missing_keys = f.loc[f._merge.eq('left_only'),['station','time','group','winter']]
    missing_keys.to_csv(out/'unobserved_calendar_rows.csv', index=False, encoding='utf-8-sig')
    # 기존 기상 입력 달력에는 일부 원 관측이 없는 시각도 있다. 정답을 보간하지 않는다.
    assert f._merge.eq('both').sum() == len(raw), 'Raw observation outside existing calendar'
    assert f.loc[f._merge.eq('left_only'),TARGETS].isna().all().all()
    f = f.drop(columns='_merge').sort_values(['station','time']).reset_index(drop=True)
    f.to_parquet(out/'development.parquet', index=False, compression='zstd')
    matched = f.groupby(['group','station','winter']).agg(rows=('time','size'), **{t:(t,'count') for t in TARGETS}).reset_index()
    matched.to_csv(out/'matched_availability.csv', index=False, encoding='utf-8-sig')
    write(out/'source_inventory.json', dict(signatures=signatures, csv_members=members, cached_files=cache_files))
    assert verify_preserved() == frozen
    receipt = dict(status='weather_targets_prepared', raw_rows=len(raw), matched_rows=len(f),
        raw_rows_not_in_existing_feature_calendar=0, feature_calendar_rows_without_raw_observation=len(missing_keys),
        identifier_only_skipped_rows=omitted, physical_bounds_removed=bounds_removed,
        targets_only_no_surface_state_or_road_temperature_read=True, protected_targets_read=False,
        target_sha256=sha(out/'targets.parquet'), data_sha256=sha(out/'development.parquet'),
        source_inventory_sha256=sha(out/'source_inventory.json'), preservation=frozen,
        stations_with_observations={t: sorted(raw.loc[raw[t].notna(),'station'].unique()) for t in TARGETS})
    write(out/'receipt.json', receipt); print(receipt, flush=True)


if __name__ == '__main__': main()
