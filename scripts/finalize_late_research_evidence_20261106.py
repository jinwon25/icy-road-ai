"""AWS 단기 이력의 미채택 근거와 재집계를 현재 제출 작업본에 연결한다."""
from pathlib import Path
import sys,json,subprocess,os
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model';D=W/'icy_road_documents'
def main():
    s=(ROOT/'scripts/integrate_short_forcing_and_navigation_20261106.py').read_text('utf8')
    s=s[:s.index("    p=B/'README.md';s=")]
    s=s.replace("E=P/'short_forcing_icing_20261106'","E=P/'aws_short_forcing_icing_20261106'").replace('short_forcing_review','aws_short_forcing_review').replace('short_forcing_comparison','aws_short_forcing_comparison')
    s=s.replace('ASOS air and ground temperature proxies; not the paper observed-pavement input or future-onset target','Nearby AWS cooling, thaw, drying and rain histories plus current ASOS. No observed pavement state or temperature; not future-onset prediction.')
    s+="\nif __name__=='__main__':main()\n"
    p=ROOT/'scripts/integrate_aws_short_forcing_20261106.py';assert not p.exists();p.write_text(s,'utf8')
    r=subprocess.run([sys.executable,'-X','utf8',str(p)],cwd=ROOT,capture_output=True,text=True,encoding='utf8',timeout=120);assert r.returncode==0,r.stdout+r.stderr
    s=(ROOT/'scripts/portable_short_forcing_review_20261106.py').read_text('utf8').replace('results/evaluation/short_forcing_review','results/evaluation/aws_short_forcing_review')
    (B/'code/analyze_aws_short_forcing_review.py').write_text(s,'utf8')
    addition='''

ASOS 원 관측의 갱신 간격을 확인한 뒤, 가까운 AWS의 10·30·120분 냉각·해빙·건조·강수 이력을 별도 비교했다. 이 후보도 20개 모형과 16개 내부 문턱 검토를 수행했다. 지역 제외 F1 0.0039로 채택 조건을 충족하지 못했고 기존에 검출한 결빙 사건도 더 놓쳤다. 두 실험의 정밀도 제약 탐색은 모두 내부 기준을 만족하는 후보를 찾지 못했다. [AWS 이력 검토](technical/aws_short_forcing_review.json)에 결과를 남겼으며, 현재 제출 모형과 필수 예측값은 유지했다.

프로젝트 보관본으로 받은 Anthropic Frontend Design·Webapp Testing과 Vercel Web Design Guidelines를 화면 검토에 사용했다. GitHub 연결 도구로 받은 9개 파일은 원본 Git blob 해시와 정확히 대조했다. [Clima의 비교 화면](https://dribbble.com/shots/26240563--Clima-dashboard)과 [Weather Monitoring Dashboard](https://dribbble.com/shots/27400006-Weather-Monitoring-Dashboard)의 공개 설명·검색 미리보기도 참고했다. 일부 원본 이미지의 직접 열람은 연결 제한으로 완료하지 못했다. 디자인 이미지·상표·예시 수치는 산출물에 복제하지 않았다.
'''
    p=B/'AI_USAGE.md';s=p.read_text('utf8')+addition;p.write_text(s,'utf8')
    d=s.replace('results/evaluation/fixed_temperature_rule_review/comparison.csv','data/fixed_temperature_rule_comparison.csv')
    for stem in ['threshold_selection_review','short_forcing_review','aws_short_forcing_review']:d=d.replace('technical/'+stem+'.json','data/'+stem+'.json')
    (D/'AI_USAGE.md').write_text(d,'utf8')
    p=B/'README.md';s=p.read_text('utf8');old='    python code/analyze_short_forcing_review.py --output local_review/short_forcing_review';assert s.count(old)==1
    p.write_text(s.replace(old,old+'\n    python code/analyze_aws_short_forcing_review.py --output local_review/aws_short_forcing_review'),'utf8')
    p=D/'README.md';s=p.read_text('utf8');s+='\n가까운 AWS의 단기 이력 후보도 [비교 원표](data/aws_short_forcing_comparison.csv)와 [검토 범위](data/aws_short_forcing_review.json)에 포함했다. 두 연구 후보는 제출 판정에 채택하지 않았다.\n';p.write_text(s,'utf8')
    print('Integrated both 20-fit studies; production models and required predictions preserved',flush=True)
if __name__=='__main__':main()
