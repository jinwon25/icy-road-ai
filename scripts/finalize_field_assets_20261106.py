"""화면 문구와 지형 이용조건을 정리하고 제출용 경로에 최종 자산을 생성한다."""
from pathlib import Path
import shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
B=ROOT/'outputs/private/evening_refinement_20261106/icy_road_model'
def main():
    template=ROOT/'scripts/field_plan_template_20261106.html'
    text=template.read_text('utf8').replace('–','-')
    text=text.replace('Copernicus GLO-30 지형 맥락에 근거한 계획. 선정되지 않은 구간의 안전이나 실제 결빙 빈도를 검증한 결과가 아니다.</p>',
        'Copernicus GLO-30 지형 맥락에 근거한 계획. 선정되지 않은 구간의 안전이나 실제 결빙 빈도를 검증한 결과가 아니다.<br>Terrain context produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.</p>')
    template.write_text(text,'utf8')
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/build_evening_field_plan_20261106.py')],check=True)
    target=B/'local_review/field_final'
    subprocess.run([sys.executable,'-X','utf8',str(B/'code/build_field_plan.py'),'--output',str(target)],check=True)
    for path in target.iterdir():shutil.copyfile(path,B/'results/field'/path.name)
if __name__=='__main__':main()
