"""첫 화면에서 위치를 바로 볼 수 있도록 설명과 기록 동작을 정리한다."""
from pathlib import Path
import shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
B=ROOT/'outputs/private/evening_refinement_20261106/icy_road_model'
def main():
    p=ROOT/'scripts/field_plan_template_20261106.html';s=p.read_text('utf8')
    changes=[
        ('기준 조합에 남은 서해안 3구간을 두 범위로 묶었다. 이 세 구간은 같은 기상 입력을 공유한다. 도로의 차이를 확인하려면 기상 조건이 같은 인접 구간과 노면온도·수분·관리 이력을 함께 비교해야 한다.',
         '서해안 3구간을 두 범위로 묶고, 같은 기상을 공유하는 인접 비선정 구간을 짝지었다. 노면온도·수분·관리 이력을 비교하기 위한 계획이다.'),
        ('아래 A는 선정 범위의 대표 중점, B는 같은 기상 입력을 공유하는 가장 가까운 비선정 구간이다. 모두 계측 계획용 좌표이며 실제 현장 확인과 측정은 아직 수행하지 않았다.',
         '지도 A는 선정 범위의 대표 중점, B는 인접 비교 후보다. 실제 위치 확인과 측정은 수행 전이다.'),
        ('step="0.1"','step="any"'),
        ('<a href="../../maps/sections.html">구간 검토</a>',
         '<a href="../../index.html#benchmarks">노면온도 평가</a><a href="../../maps/sections.html">구간 검토</a>'),
        ("$('csv').onclick=()=>{const value=collect().fields;",
         "$('csv').onclick=()=>{const invalid=[...document.querySelectorAll('input')].find(e=>!e.checkValidity());if(invalid){const d=invalid.closest('details');if(d)d.open=true;invalid.reportValidity();status('입력값의 범위를 확인한 뒤 CSV를 저장하세요. 측정하지 않은 값은 비워 둡니다.');return;}const value=collect().fields;")]
    for old,new in changes:
        assert s.count(old)==1,(old,s.count(old));s=s.replace(old,new)
    start=s.index('<div class="actions global-actions">')
    end=s.index('<nav class="area-tabs"',start)
    top='''<div class="actions global-actions"><a class="button" href="field_measurement_plan.pdf">계획서 PDF 열기</a><button id="startRecord" type="button">현장 기록 작성</button></div>
'''
    s=s[:start]+top+s[end:]
    old='<div id="cases"></div>'
    new='''<div id="cases"></div>
<div class="actions global-actions"><button id="csv" type="button">현장 기록 CSV 저장</button><button id="save" type="button">작성 내용 파일로 저장</button><button id="load" type="button">작성 파일 불러오기</button><button id="print" type="button">두 범위 인쇄</button><input class="hidden" id="file" type="file" accept="application/json,.json"></div>
<p id="status" class="save-status" role="status" aria-live="polite">측정하지 않은 값은 비워 두고, 작성한 내용은 CSV나 파일로 저장할 수 있습니다.</p>'''
    assert s.count(old)==1;s=s.replace(old,new)
    old="$('print').onclick=()=>window.print();"
    new="$('startRecord').onclick=()=>{const d=$('S01').querySelector('details');d.open=true;d.scrollIntoView({block:'start'});};$('print').onclick=()=>window.print();"
    assert s.count(old)==1;s=s.replace(old,new)
    p.write_text(s,'utf8')
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/build_evening_field_plan_20261106.py')],check=True)
    target=B/'local_review/field_polished'
    subprocess.run([sys.executable,'-X','utf8',str(B/'code/build_field_plan.py'),'--output',str(target)],check=True)
    for path in target.iterdir():shutil.copyfile(path,B/'results/field'/path.name)
if __name__=='__main__':main()
