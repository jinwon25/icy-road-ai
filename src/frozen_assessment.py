"""고정된 개발 후보만 평가한다. 보호 타깃의 정답은 입력 생성기에 전달하지 않는다."""
import json
from pathlib import Path
from src.data_source import sha256_file
from src.validation import PROTECTED_STATIONS, canonical_station_id


def verify_freeze(root: Path):
    path = root / 'outputs/private/frozen_assessment_v1/freeze.json'
    frozen = json.loads(path.read_text(encoding='utf-8'))
    if frozen['protected_outcomes_opened_at_freeze']:
        raise ValueError('Freeze must precede protected outcome assessment')
    if set(frozen['target_stations']) != PROTECTED_STATIONS:
        raise ValueError('Unexpected frozen targets')
    for relative, digest in frozen['files'].items():
        if sha256_file(root / relative) != digest:
            raise ValueError(f'Frozen input changed: {relative}')
    return frozen


def protected_point_inputs(builder, point, times, frozen):
    """평가 전용 정적 메타데이터를 익명 위치로 변환한다. 참조 풀은 계속 개발 14곳이다."""
    allowed = {'station', 'route', 'lat', 'lon', 'elevation_m'}
    if set(point) != allowed:
        raise ValueError('Only complete static target metadata is accepted')
    sid = canonical_station_id(point['station'])
    if sid not in PROTECTED_STATIONS or sid not in frozen['target_stations']:
        raise ValueError('Not a frozen protected target')
    # 일반 개발 입력기의 보호 타깃 거부 규칙을 유지한다. 이 함수는 평가 고정 확인 후만 호출한다.
    location = {key: point[key] for key in ('route', 'lat', 'lon')}
    location['station'] = 'frozen_target_' + sid
    features, mapping = builder.build(location, times, forbidden=PROTECTED_STATIONS)
    for key in ('near_source', 'moisture_source'):
        if mapping[key] in PROTECTED_STATIONS:
            raise ValueError('Protected reference is forbidden during final assessment')
    features['station'] = sid
    features['elevation_m'] = float(point['elevation_m'])
    return features, mapping
