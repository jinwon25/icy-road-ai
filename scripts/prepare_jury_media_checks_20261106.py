"""현재 보고서와 계측 화면을 포함한 실제 영상·화면 검증 코드를 준비한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    s=(ROOT/'scripts/audit_evening_media_20261106.py').read_text('utf8')
    s=s.replace("W=ROOT/'outputs/private/evening_refinement_20261106'","W=ROOT/'outputs/private/final_jury_review_20261106'")
    s=s.replace("O=W/'media_review_final'","O=W/'media_review_jury'")
    s=s.replace('selected=[3,13,19,28,35,41,47,54,63,70,76,min(84,seconds-2)]',
                'selected=[3,13,19,28,35,43,49,56,63,70,78,min(91,seconds-2)]')
    (ROOT/'scripts/audit_jury_media_20261106.py').write_text(s,'utf8')
    s=(ROOT/'scripts/audit_evening_field_20261106.py').read_text('utf8')
    s=s.replace("W=ROOT/'outputs/private/evening_refinement_20261106'","W=ROOT/'outputs/private/final_jury_review_20261106'")
    s=s.replace("O=W/'field_browser_final'","O=W/'field_browser_jury'")
    s=s.replace("page.pdf(path=str(F/'field_measurement_plan.pdf'),print_background=True,prefer_css_page_size=True)",
                "assert (F/'field_measurement_plan.pdf').is_file()")
    (ROOT/'scripts/audit_jury_field_20261106.py').write_text(s,'utf8')
if __name__=='__main__':main()
