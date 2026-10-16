"""추가 연구·문서·4쪽 PDF가 검산 근거와 일치하고 후보를 보존했는지 확인한다."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read, write, preservation
from src.data_source import sha256_file as sha

PRIVATE = ROOT / 'outputs/private'
OUT = PRIVATE / 'air_road_gap_quality_20261016_v1'


def main():
    if OUT.exists():
        raise FileExistsError('Preserve completed followup quality receipt')
    frozen = preservation()
    folder = PRIVATE / 'air_road_blending_20261016_v1'
    rules = read(folder / 'summary.json')
    audit = read(folder / 'independent_verification.json')
    assert audit['status'] == 'independent_air_road_blending_audit_passed'
    assert audit['summary_sha256'] == sha(folder / 'summary.json')
    assert rules['policies'] == 72 and rules['new_model_fits'] == 0 and rules['model_promoted'] is False
    assert len(rules['choices']) == 4
    assert all(v == {'research': 'air_zero', 'strict': 'current'} for v in rules['choices'].values())
    assert rules['retrospective_best_fixed_policy'] == 'air_t+0.0_none_n1_union0'
    folder = PRIVATE / 'asos_gap_fallback_20261016_v1'
    gaps = read(folder / 'summary.json')
    audit = read(folder / 'independent_verification.json')
    assert audit['status'] == 'independent_asos_gap_fallback_audit_passed' and audit['summary_sha256'] == sha(folder / 'summary.json')
    assert gaps['masked_validation_rows'] == 648 and sum(r['quality_passed'] for r in gaps['masked_station_results']) == 2
    assert gaps['reference_binary_available'] == 12 and gaps['reference_still_missing'] == 6
    assert not gaps['all_station_quality_gates_passed'] and not gaps['execution_candidate_changed']
    weather = read(PRIVATE / 'weather_source_gap_audit_20261016_v1/receipt.json')
    assert weather['status'] == 'official_weather_source_gap_audit_passed' and weather['aws_api_http_status'] == 403
    assert weather['available_pre_winter_asos_rows'] == 6 and weather['completion_of_prediction_gaps_qualified'] is False
    metadata = read(PRIVATE / 'remaining_station_metadata_20261016_v1/receipt.json')
    assert metadata['status'] == 'remaining_station_metadata_audit_passed' and metadata['eligible_under_previous_screen'] == 0
    report = PRIVATE / 'air_road_gap_report_20261016_v1'
    receipt, visual = read(report / 'report_receipt.json'), read(report / 'visual_review.json')
    pdf = report / 'followup_report.pdf'
    assert sha(pdf) == receipt['pdf_sha256'] == visual['pdf_sha256']
    assert visual['status'] == 'all_four_rendered_pages_visually_reviewed' and visual['pages_reviewed'] == [1, 2, 3, 4]
    assert not any(visual[k] for k in ['clipping', 'overlap', 'broken_glyphs'])
    for name, digest in receipt['evidence_signatures'].items():
        assert sha(ROOT / name) == digest, name
    assert sha(ROOT / 'scripts/build_air_road_gap_report.py') == receipt['source_sha256']
    for name, digest in visual['preview_signatures'].items():
        assert sha(report / 'preview' / name) == digest
    document = ROOT / 'docs/research/AIR_ROAD_AND_INPUT_GAPS_20261016.md'
    text = document.read_text(encoding='utf-8')
    with fitz.open(pdf) as doc:
        assert len(doc) == 4 and sum(len(p.get_links()) for p in doc) == 10
        pdf_text = '\n'.join(p.get_text() for p in doc)
    for name, label in [('current', '현재 온도·수분 후보'), ('always_one', '항상 결빙'), ('road_zero', '추정 노면온도 ≤0°C'),
                        ('air_zero', 'ASOS 기온 ≤0°C'), ('nested_research', '내부 선택: 연구용 F1'), ('nested_strict', '내부 선택: 엄격 기준')]:
        r = rules['reports'][name]
        metric = r['daily']['144']
        row = f"| {label} | {metric['f1_available_station_mean']:.6f} | {metric['f1_days']}/{metric['f1_stations']} | {r['fp']:,} | {r['fn']:,} | {r['event']['detected']}/347 |"
        assert row in text, name
        for value in [f"{metric['f1_available_station_mean']:.6f}", f"{r['fp']:,}", f"{r['fn']:,}", f"{r['event']['detected']}/347"]:
            assert value in pdf_text, (name, value)
    for number in ['44,714,016', '1,242,056', '788', '387', '648', '666', '1,296', '403']:
        assert number in text and number in pdf_text, number
    official = read(PRIVATE / 'official_updates_20261016_v2/completion_receipt.json')
    assert not official['changed_details'] and not official['changed_tabs'] and official['blank_application_unchanged']
    candidate = PRIVATE / 'submission_candidate_20261016_v1.zip'
    expected = '80de76bb5da5c9004dc72f066ac45f0221d96a5fd7cf9982c6ba963072f25989'
    assert sha(candidate) == rules['execution_candidate_archive_sha256'] == gaps['execution_candidate_archive_sha256'] == expected
    assert preservation() == frozen
    OUT.mkdir()
    result = dict(status='air_road_followup_quality_passed', checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  fixed_policies=72, selection_groups=4, masked_rows=648, weather_request_count=7,
                  new_eligible_independent_stations=0, new_model_fits=0, protected_or_opened_outcomes_read=False,
                  report_pages=4, report_links=10, source_document_sha256=sha(document), report_pdf_sha256=sha(pdf),
                  execution_candidate_unchanged=True, execution_candidate_archive_sha256=expected,
                  old_frozen_files=frozen[0], reserved_frozen_files=frozen[1])
    write(OUT / 'quality_receipt.json', result)
    print(result, flush=True)


if __name__ == '__main__':
    main()
