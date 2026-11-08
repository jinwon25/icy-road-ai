"""검증된 제출본을 보존하고 심사 관점의 추가 검토 작업본을 준비한다."""
from pathlib import Path
from datetime import datetime,timezone
import json,shutil
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'outputs/private/final_jury_review_20261106';S=ROOT/'outputs/private/competition_submission'
def main():
    assert not W.exists();W.mkdir()
    shutil.copy2(S/'submission_receipt.json',W/'baseline_receipt.json')
    for n in ['icy_road_model','icy_road_documents']:
        shutil.copytree(S/n,W/n,ignore=shutil.ignore_patterns('local_review','__pycache__','*.pyc'))
    for n in ['docs/competition/COMPETITION_REQUIREMENTS.md','docs/STATUS.md','README.md','docs/START_HERE.md']:
        p=ROOT/n
        if p.is_file():
            q=W/'documents_before_review'/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
    plan=dict(at_utc=datetime.now(timezone.utc).isoformat(),
        priority=['검증 기간 전체의 코어 모델 입력·추론 재현','기존 취약구간 목록과 현재 공간 기준의 관계를 기술',
                  '공식 요구·현재 결과가 서로 다른 안내 문서 정리','중요 한계와 반복 문구를 구분한 편집·화면 개선'],
        rubric={'creativity':20,'excellence':50,'effectiveness':30},
        claim_limits=['경쟁팀 결과나 비공개 심사점수 없이 수상확률·예상순위를 산출하지 않음',
                      '공개 목록 미포함 구간을 안전한 음성 정답으로 사용하지 않음',
                      '동일 기상 입력을 공유하는 500m 구간을 독립 관측 표본으로 세지 않음'],
        protected_outcomes_used_to_retune_model=False,model_changes_planned=False,competition_submitted=False,
        public_sources=[
            'https://aida.kisti.re.kr/competition/main/overview.do',
            'https://scikit-learn.org/stable/modules/classification_threshold.html',
            'https://gmd.copernicus.org/articles/12/3481/2019/gmd-12-3481-2019.html',
            'https://ops.fhwa.dot.gov/publications/fhwahop20051/index.htm'])
    (W/'review_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n','utf8')
    print('심사 검토 작업본을 준비했습니다.',flush=True)
if __name__=='__main__':main()
