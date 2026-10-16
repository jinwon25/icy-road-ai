"""과거에 고정한 위치 선별표에서 아직 미조회인 독립 지점의 수를 갱신한다."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read, write, preservation
from src.data_source import sha256_file as sha

PRIVATE = ROOT / 'outputs/private'
OUT = PRIVATE / 'remaining_station_metadata_20261016_v1'


def main():
    if OUT.exists():
        raise FileExistsError('Preserve completed metadata screen update')
    frozen = preservation()
    previous = PRIVATE / 'temperature_mean_validation_design_20261010_v1'
    design = read(previous / 'design_receipt.json')
    assert sha(previous / 'metadata_screen.csv') == design['screen_sha256']
    for name, digest in design['static_source_signatures'].items():
        assert sha(ROOT / name) == digest, name
    screen = pd.read_csv(previous / 'metadata_screen.csv', dtype={'station': str})
    used = set()
    signatures = {}
    # Only request metadata is opened, never observation/evaluation parquets.
    for path in sorted(PRIVATE.rglob('download_manifest.json')):
        manifest = read(path)
        for record in manifest.get('records', {}).values():
            if isinstance(record, dict) and 'station' in record:
                used.add(str(record['station']))
        signatures[str(path.relative_to(ROOT))] = sha(path)
    screen['subsequently_requested'] = screen.station.isin(used)
    screen['currently_unrequested'] = ~screen.subsequently_requested
    screen['eligible_under_previous_screen'] = screen.currently_unrequested & screen.upper_distance_screen_passed & screen.spatial_separation_passed
    unrequested = screen.loc[screen.currently_unrequested]
    assert len(screen) == 32 and len(unrequested) == 30
    in_bounds = unrequested.loc[unrequested.upper_distance_screen_passed]
    assert in_bounds.station.tolist() == ['12208']
    assert not screen.eligible_under_previous_screen.any()
    OUT.mkdir()
    screen.to_csv(OUT / 'updated_metadata_screen.csv', index=False)
    write(OUT / 'request_manifest_signatures.json', signatures)
    assert preservation() == frozen
    receipt = dict(status='remaining_station_metadata_audit_passed', checked_at_utc=datetime.now(timezone.utc).isoformat(),
                   prior_screen_candidates=32, subsequently_requested_stations=sorted(set(screen.station) & used),
                   currently_unrequested=30, unrequested_within_unchanged_weather_bounds=1,
                   within_bounds_station='12208', within_bounds_nearest_known_road_km=float(in_bounds.known_road_min_km.iloc[0]),
                   minimum_separation_km=design['metadata_minimum_separation_km'], eligible_under_previous_screen=0,
                   scope='20261010 frozen static catalogue and existing unchanged weather cache; not a national station availability claim',
                   road_outcomes_read=False, network_requests=0, new_predictions_generated=False,
                   previous_design_sha256=sha(previous / 'design_receipt.json'), screen_sha256=sha(OUT / 'updated_metadata_screen.csv'),
                   request_manifests_checked=len(signatures), old_frozen_files=frozen[0], reserved_frozen_files=frozen[1])
    write(OUT / 'receipt.json', receipt)
    print(receipt, flush=True)


if __name__ == '__main__':
    main()
