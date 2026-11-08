"""새 요약 화면 링크를 생성 템플릿과 실제 출력에 함께 맞춘다."""
from pathlib import Path
import sys,subprocess,os,json,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model'
def main():
    p=B/'index.html';s=p.read_text('utf8');old='<h2>결빙 판정과 관측 결빙일</h2>';assert s.count(old)==1
    p.write_text(s.replace(old,'<h2 id="classification">결빙 판정과 관측 결빙일</h2>'),'utf8')
    for relative,prefix in [('assets/inspection_template.txt','../'),('assets/field_plan_template.html','../../')]:
        p=B/relative;s=p.read_text('utf8');old=f'<a class="team-brand" href="{prefix}index.html">';assert old in s
        p.write_text(s.replace(old,f'<a class="team-brand" href="{prefix}start.html">',1),'utf8')
    env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1'
    r=subprocess.run([sys.executable,'-X','utf8','code/build_field_plan.py','--output','local_review/late_field'],cwd=B,env=env,capture_output=True,text=True,encoding='utf8',timeout=240)
    assert r.returncode==0,r.stdout+r.stderr
    for name in ['comparison_candidates.csv','measurement_protocol.csv','field_cases.json','index.html']:
        assert sha(B/'local_review/late_field'/name)==sha(B/'results/field'/name),name
    shutil.copyfile(B/'local_review/late_field/summary.json',B/'results/field/summary.json')
    print('PASS navigation sources and field plan generated HTML match',flush=True)
if __name__=='__main__':main()
