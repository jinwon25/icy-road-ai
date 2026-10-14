"""실제로 확인한 공식 사실과 미확정 제출 날짜를 기계가 읽는 설정으로 기록한다."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/official_updates_20261013_v1'
TARGET = ROOT / 'config/official_requirements_20261013.json'


def main():
    if TARGET.exists():
        raise FileExistsError('Preserve requirement snapshot')
    changes = json.loads((OUT / 'change_comparison.json').read_text('utf-8')); answers = json.loads((OUT / 'answer_comparison.json').read_text('utf-8'))
    faq = (OUT / 'notice_639_nttCn_clean.md').read_text('utf-8')
    notice = (OUT / 'notice_564_nttCn_clean.md').read_text('utf-8')
    ai = (OUT / 'general_qa_618_reply_nttCn_clean.md').read_text('utf-8')
    assert '23:59' in faq and '한국 시간' in notice and '아직 시작되지' in notice
    assert '자필서명 필수' in (OUT / 'application_new_body.txt').read_text('utf-8')
    assert '원칙적으로 허용되지' in ai and '생성형 AI를 활용' in ai
    assert all(t['exact_content_equal'] for t in changes['tabs']) and all(r['normalized_bodies_equal'] for r in answers['problem_questions'].values())
    assert not answers['problem_questions']['633']['official_answer_present']
    sources = {}
    for r in json.loads((OUT / 'fetch_receipts.json').read_text('utf-8')):
        if r['name'] in ['problem_page', 'problem_tabs', 'notice_639', 'notice_564', 'general_qa_632', 'general_qa_618', 'problem_qa_588', 'problem_qa_633', 'current_application']:
            sources[r['name']] = dict(url=r['url'], response_sha256=r['sha256'], status=r['status'])
    facts = dict(checked_date_kst='2026-10-13', timezone='Asia/Seoul', problem_id='PROB_000000000004604',
                 application_deadline_date='2026-11-06', application_deadline_is_result_deadline=False,
                 result_submission=dict(open_as_of_check=False, opening_date=None, deadline_date=None, deadline_time_if_announced='23:59', timezone='Asia/Seoul', schedule_status='운영진 별도 공지 대기',
                                        status_basis='공개 공지564와 일반 답변632 기준', authenticated_submission_form_verified=False),
                 application=dict(handwritten_signature_required=True, typed_signature_rejected=True, previous_bytes=133120, current_bytes=222720,
                                  current_sha256=changes['extracted']['application_new']['sha256'], submitted_application_modified=False, participant_account_approval_verified=False),
                 ai=dict(design_and_development_assistance_allowed=True, usage_and_review_record_required=True, external_api_direct_analysis_or_prediction='원칙적 비허용; 문제별 제한사항 별도 확인',
                         public_weather_data_training='문제별588 답변에서 출처·근거 제시 조건으로 허용', evaluation_time_raw_data_api_access='명시적 추가 답변 미확인',
                         project_inference='캐시·로컬 저장 모델 기반; 검토 패키지 외부 예측 API 호출0'),
                 evaluation=dict(problem_and_data_content_unchanged=True, displayed_release='20261007', full_zip_byte_identity_verified=False, official_ice_code='04',
                                 known_non_ice_codes=['01', '02', '03', '10', '11', '12', '13', '14', '15'], qa633_answer_present=False,
                                 incomplete_day_policy_status='미확정', single_metric_zero_denominator_policy_status='미확정', csv_schema_status='해당 문제의 구체 규격 미확정',
                                 faq_screenshot_schema_applies_to_this_problem=False),
                 sources=sources, external_publication_made=False, competition_submission_made=False)
    TARGET.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding='utf-8'); print('Requirements saved', TARGET)


if __name__ == '__main__':
    main()
