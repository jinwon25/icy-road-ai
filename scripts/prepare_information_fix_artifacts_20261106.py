"""정보 중복을 제거한 기준의 분석·도표 작업을 준비한다."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/judging_upgrade_20261106';B=W/'icy_road_model'
shutil.copyfile(ROOT/'src/inspection_sensitivity.py',B/'src/inspection_sensitivity.py')
s=(ROOT/'scripts/analyze_inspection_sensitivity_20261106.py').read_text('utf8')
s=s.replace("O=W/'inspection_sensitivity'","O=W/'information_sensitivity'").replace('len(selected)==22','len(selected)==3')
s=s.replace('q.prediction_group.nunique()','q.weather_information_group.nunique()')
old="target=B/'results/sections/sensitivity';shutil.copytree(O,target)"
new="""target=B/'results/sections/sensitivity';previous=W/'sensitivity_before_information_fix'
    assert target.resolve().is_relative_to(W.resolve()) and previous.resolve().is_relative_to(W.resolve()) and not previous.exists()
    target.rename(previous);shutil.copytree(O,target)"""
assert old in s;s=s.replace(old,new)
p=ROOT/'scripts/analyze_information_sensitivity_20261106.py';assert not p.exists();p.write_text(s,'utf8')
print('정보 중복 보정 기준의 75조합 분석 준비')
