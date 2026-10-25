"""전국 ASOS 위치 이력으로 추가 도로 검증 후보를 선별한다. 노면 관측 파일은 열지 않는다."""
import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import PROTECTED_STATIONS
from src.data_source import sha256_file as sha
from scripts.evaluate_synoptic_icing import read, write
from scripts.evaluate_method_blending import preservation


def distances(lat, lon, others):
    a, b = np.radians(float(lat)), np.radians(float(lon))
    c, d = np.radians(others.lat.to_numpy(float)), np.radians(others.lon.to_numpy(float))
    h = np.sin((c-a)/2)**2 + np.cos(a)*np.cos(c)*np.sin((d-b)/2)**2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def unused_candidates(roads, used):
    return roads.loc[roads.independent_station_candidate & roads.target_route_candidate
                     & ~roads.already_in_competition_scope & ~roads.station.isin(set(used) | set(PROTECTED_STATIONS))].copy()


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', required=True, type=Path)
    out = p.parse_args().output.resolve(); cfg = ROOT / 'config/expanded_icing_validation_20261025.json'; plan = read(cfg)
    if out.exists() or not out.is_relative_to((ROOT / 'outputs/private').resolve()):
        raise ValueError('New private directory required')
    frozen = preservation(); history = ROOT / plan['history']; roadpath = ROOT / plan['road_catalog']
    raw = pd.read_csv(history, encoding='cp949').rename(columns={'지점':'asos_station', '시작일':'start', '종료일':'end', '지점명':'asos_name', '위도':'lat', '경도':'lon'})
    raw.start = pd.to_datetime(raw.start); raw.end = pd.to_datetime(raw.end)
    lo = min(pd.Timestamp(w[0]) for w in plan['winters']); hi = max(pd.Timestamp(w[1]) for w in plan['winters'])
    weather = raw.loc[raw.start.le(lo) & (raw.end.isna() | raw.end.ge(hi))].dropna(subset=['lat', 'lon']).copy()
    duplicates = weather.asos_station.duplicated(keep=False); ambiguous = weather.loc[duplicates, 'asos_station'].tolist()
    weather = weather.loc[~duplicates].sort_values('asos_station').reset_index(drop=True)
    roads = pd.read_csv(roadpath, dtype={'station':str}); used = set(PROTECTED_STATIONS); manifests = {}
    for path in sorted((ROOT / 'outputs/private').rglob('download_manifest.json')):
        manifest = read(path)
        for record in manifest.get('records', {}).values():
            if isinstance(record, dict) and 'station' in record:
                used.add(str(record['station']))
        manifests[path.relative_to(ROOT).as_posix()] = sha(path)
    known = roads.loc[roads.station.isin(used) | roads.already_in_competition_scope].copy()
    candidates = unused_candidates(roads, used)
    rows = []
    for row in candidates.itertuples():
        dd = distances(row.lat, row.lon, weather); i = int(dd.argmin())
        kd = distances(row.lat, row.lon, known)
        rows.append(dict(station=row.station, name=row.name, route=row.route, station_type=row.station_type,
            lat=row.lat, lon=row.lon, asos_station=int(weather.iloc[i].asos_station), asos_name=weather.iloc[i].asos_name,
            asos_distance_km=float(dd[i]), known_road_min_km=float(kd.min())))
    table = pd.DataFrame(rows)
    table['eligible'] = table.asos_distance_km.le(plan['maximum_asos_km']) & table.known_road_min_km.ge(plan['minimum_known_road_km'])
    chosen = []
    for row in table.loc[table.eligible].sort_values(['known_road_min_km','asos_distance_km','station'], ascending=[False,True,True]).itertuples():
        if chosen and distances(row.lat, row.lon, table.loc[table.station.isin(chosen)]).min() < plan['minimum_selected_separation_km']:
            continue
        chosen.append(row.station)
        if len(chosen) == plan['maximum_selected']:
            break
    assert not set(chosen) & used
    table['selected'] = table.station.isin(chosen); out.mkdir(parents=True)
    table.to_csv(out / 'screen.csv', index=False)
    weather[['asos_station','asos_name','start','end','lat','lon']].to_csv(out / 'asos_history_screen.csv', index=False)
    write(out / 'request_manifest_signatures.json', manifests)
    assert preservation() == frozen
    receipt = dict(status='expanded_weather_metadata_screened', weather_history_rows=len(raw), usable_asos_locations=len(weather),
        ambiguous_station_ids=ambiguous, unrequested_candidates=len(table), distance_eligible=int(table.eligible.sum()),
        selected_stations=chosen, selected_weather_stations=sorted(table.loc[table.selected,'asos_station'].unique().tolist()),
        source_signatures={cfg.relative_to(ROOT).as_posix():sha(cfg), plan['history']:sha(history), plan['road_catalog']:sha(roadpath)},
        screen_sha256=sha(out / 'screen.csv'), code_sha256=sha(Path(__file__)), road_outcomes_read=False,
        new_independent_assessment=False, frozen_counts=list(frozen))
    write(out / 'receipt.json', receipt); print(receipt, flush=True)
    print(table.loc[table.selected].to_string(index=False), flush=True)


if __name__ == '__main__':
    main()
