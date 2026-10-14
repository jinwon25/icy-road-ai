"""평가 그룹을 제외한 오차로 온도 두 후보의 경험적90% 범위를 계산한다."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from src.temperature_uncertainty import residual_radius, empirical_interval, interval_report
from scripts.evaluate_method_blending import read, write, preservation, PRIVATE

SOURCE = PRIVATE / 'temperature_pair_blending_20261010_v1'
OUT = PRIVATE / 'temperature_uncertainty_20261010_v1'
METHODS = ['weather_mse300', 'equal_distance_mse_mae300']
PLAN = dict(nominal_fraction=.9, methods=METHODS, quantile='고정 지점 균등 가중 절대 OOF 오차 경험적90분위수',
            source='반복 개발에서 선택한 고정 온도 후보. 독립 성능 아님.',
            calibration='G의 오차 범위는 G와 H를 모두 제외한 모델의 H 예측으로 계산. G 정답 미사용.',
            coverage='공간·시계열의 교환가능성이 입증되지 않았고 보정 모델과 최종 모델의 학습 크기도 다름.90% 포함 보장 없음.',
            boundary='노면온도0도 경계의 애매함만 표현. 공식04 결빙 확률·위험 등급·안전 판정이 아님.',
            no_new_model_fits=True, no_assessment_outcomes=True)


def main():
    if OUT.exists():
        raise FileExistsError('Preserve completed interval study')
    freezes = preservation(); audit = read(SOURCE / 'independent_verification.json')
    if audit['status'] != 'independent_fixed_pairs_audit_passed' or audit['summary_sha256'] != sha(SOURCE / 'summary.json'):
        raise ValueError('Audited mean predictions required')
    groups = read(SOURCE / 'groups.json'); OUT.mkdir(); write(OUT / 'experiment_plan.json', PLAN)
    shutil.copy2(Path(__file__), OUT / 'analysis_source.py'); shutil.copy2(ROOT / 'src/temperature_uncertainty.py', OUT / 'uncertainty_source.py')
    signatures = {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / 'src/temperature_uncertainty.py', ROOT / 'src/method_blending.py', SOURCE / 'summary.json', SOURCE / 'independent_verification.json', SOURCE / 'groups.json']}
    parts, calibrations = [], {}
    columns = ['station', 'time', 'group', 'road_temp', *METHODS]
    for outer in groups:
        folder = SOURCE / outer
        inner_path, outer_path = folder / 'inner_oof.parquet', folder / 'outer_predictions.parquet'
        for path in [inner_path, outer_path]:
            signatures[str(path.relative_to(ROOT))] = sha(path)
        inner, query = pd.read_parquet(inner_path, columns=columns), pd.read_parquet(outer_path, columns=columns)
        assert outer not in set(inner.group) and set(query.group) == {outer}
        assert set(inner.station) == set().union(*(set(groups[g]) for g in groups if g != outer))
        calibrations[outer] = {}
        for name in METHODS:
            radius, receipt = residual_radius(inner, inner[name])
            lo, hi = empirical_interval(query[name], radius)
            query[name+'_lower'], query[name+'_upper'] = lo, hi
            calibrations[outer][name] = receipt | dict(radius=radius, calibration_groups=sorted(set(groups)-{outer}), outer_labels_used=False)
        parts.append(query)
    combined = pd.concat(parts, ignore_index=True).sort_values(['station', 'time']).reset_index(drop=True)
    combined.to_parquet(OUT / 'intervals.parquet', index=False, compression='zstd')
    reports = {name: interval_report(combined, combined[name], combined[name+'_lower'], combined[name+'_upper']) for name in METHODS}
    write(OUT / 'calibrations.json', calibrations); write(OUT / 'input_signatures.json', signatures)
    assert preservation() == freezes and all(r['n'] == 155236 for r in reports.values())
    summary = dict(status='empirical_spatial_temperature_ranges_complete', completed_at_utc=datetime.now(timezone.utc).isoformat(),
                   reports=reports, calibrations=calibrations, new_model_fits=0, assessment_outcomes_used=False, guaranteed_coverage=False,
                   old_frozen_files=freezes[0], reserved_frozen_files=freezes[1],
                   files={p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()})
    write(OUT / 'summary.json', summary)
    print(reports)


if __name__ == '__main__':
    main()
