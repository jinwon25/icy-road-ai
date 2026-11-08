"""최종 정보 단위의 화면·영상·휴대형 재현 도구를 준비한다."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/judging_upgrade_20261106';B=W/'icy_road_model';O=W/'information_group_correction'
source=(ROOT/'scripts/build_inspection_evidence_20261106.py').read_text('utf8')
source=source.replace('import sys,json,math','import sys,json,math,argparse')
source=source.replace('from scripts.seal_protected_weather_20261106 import W','')
source=source.replace("B=W/'icy_road_model'","B=ROOT")
source=source.replace('def main():','''def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.output.exists():raise FileExistsError('Choose a new output file')''')
for name in ['segment_terrain.csv','segment_solar_context.csv']:
    source=source.replace("W/'terrain_context/"+name+"'","B/'results/sections/terrain/"+name+"'")
source=source.replace("ROOT/'src/templates/inspection_evidence.html'","ROOT/'assets/inspection_template.txt'")
source=source.replace("W/'terrain_context/summary.json'","B/'data/copernicus_dem/manifest.json'").replace("['source_notice']","['derived_notice']")
source=source.replace("(B/'maps/sections.html').write_text(template,'utf8')","a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(template,'utf8')")
assert 'W/' not in source and 'outputs/private/' not in source
(B/'code/build_section_explorer.py').write_text(source,'utf8')
shutil.copyfile(ROOT/'src/templates/inspection_evidence.html',B/'assets/inspection_template.txt')
source=(ROOT/'scripts/check_judging_experience_20261106.py').read_text('utf8')
source=source.replace("O=W/'browser_review_final'","O=W/'browser_review_information'")
source=source.replace("W/'inspection_sensitivity/","B/'results/sections/sensitivity/")
source=source.replace("=='22'","=='3'").replace("count()==11","count()==2").replace("select_option('F06')","select_option('S01')")
target=ROOT/'scripts/check_information_experience_20261106.py';assert not target.exists();target.write_text(source,'utf8')
source=(ROOT/'scripts/record_judging_demo_20261106.py').read_text('utf8')
source=source.replace("'local_review/demo_inference.csv'","'local_review/demo_inference_information.csv'")
source=source.replace("W/'demo_recording'","W/'information_demo_recording'")
source=source.replace("W/'demo_build.json'","W/'demo_build_information.json'")
source=source.replace("W/'demo_selected_section.csv'","W/'demo_selected_information.csv'")
source=source.replace('기준 조합은 22구간입니다.','실제 14입력 시계열의 중복을 제거한 기준 조합은 3구간·2개 범위입니다.')
source=source.replace('F06','S01')
source=source.replace("  page.locator('#criteria').evaluate('(e)=>e.open=false')","  caption('결빙 조건 입력의 전체 시계열이 같은 조합은 한 번씩 집계했습니다. 두 겨울의 서로 다른 입력은 22개·24개입니다.',5,'실제 입력 정보 단위')\n  page.locator('#criteria').evaluate('(e)=>e.open=false')")
target=ROOT/'scripts/record_information_demo_20261106.py';assert not target.exists();target.write_text(source,'utf8')
old=B/'demo/model_demo.webm';saved=O/'model_demo_before_information_fix.webm'
assert old.resolve().is_relative_to(W.resolve()) and saved.resolve().is_relative_to(W.resolve()) and not saved.exists()
old.replace(saved)
source=(ROOT/'scripts/audit_judging_media_20261106.py').read_text('utf8')
source=source.replace("O=W/'media_review'","O=W/'media_review_information'").replace("=='22'","=='3'")
target=ROOT/'scripts/audit_information_media_20261106.py';assert not target.exists();target.write_text(source,'utf8')
print('실제 정보 단위 기준의 재현 도구·화면·영상 검증 준비 완료')
