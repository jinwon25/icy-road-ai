"""최종 작업본에 맞춘 화면·영상 재검증 명령을 준비한다."""
from pathlib import Path
import json,sys,subprocess,shutil
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/evening_refinement_20261106';B=W/'icy_road_model'
def main():
    source=(ROOT/'scripts/audit_information_media_20261106.py').read_text('utf8')
    source=source.replace("B=W/'icy_road_model';O=W/'media_review_information'", "W=ROOT/'outputs/private/evening_refinement_20261106';B=W/'icy_road_model';O=W/'media_review_final'")
    old='selected=[3,13,19,28,35,41,47,54,min(62,seconds-2)]'
    new='selected=[3,13,19,28,35,41,47,54,63,70,76,min(84,seconds-2)]'
    assert source.count(old)==1;source=source.replace(old,new).replace('(990,3*395)','(990,4*395)')
    (ROOT/'scripts/audit_evening_media_20261106.py').write_text(source,'utf8')
    source=(ROOT/'scripts/check_information_experience_20261106.py').read_text('utf8')
    source=source.replace("B=W/'icy_road_model';O=W/'browser_review_information'", "W=ROOT/'outputs/private/evening_refinement_20261106';B=W/'icy_road_model';O=W/'browser_review_final'")
    (ROOT/'scripts/check_evening_experience_20261106.py').write_text(source,'utf8')
    official=dict(status='latest_public_listings_only_rechecked',at_kst='2026-11-06 19:27',
        task_page='https://aida.kisti.re.kr/competition/main/problem/PROB_000000000004604/detail.do',
        general_qna='https://aida.kisti.re.kr/competition/main/qna.do',
        notice='https://aida.kisti.re.kr/competition/main/notice.do',
        latest_notice_titles_unchanged=True,
        new_unanswered_general_question='팀원 정보를 비회원에서 회원으로 변경한 후 승인 상태가 제출로 바뀌고 리더보드에서 사라졌습니다',
        question_answered_on_listing=False,
        latest_full_details_verified_kst='2026-11-06 15:35',
        detail_refresh_status='connection_error',task_board_refresh_status='connection_error',
        no_claim_that_later_detail_edits_were_excluded=True,
        user_confirmed_participation_approved=True,account_or_team_membership_edited=False,
        sources_were_public=True,competition_submitted=False)
    (B/'technical/official_evening_access_review.json').write_text(json.dumps(official,ensure_ascii=False,indent=2)+'\n','utf8')
    print('최종 화면·영상 검증과 공식 안내 재확인 범위를 준비했습니다.',flush=True)
if __name__=='__main__':main()
