"""계측 계획의 휴대 가능한 생성 코드와 화면 자산을 작업용 제출본에 배치한다."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/private/evening_refinement_20261106/icy_road_model'
def main():
    for source,target in [
        ('scripts/field_plan_runtime_20261106.py','code/build_field_plan.py'),
        ('scripts/field_plan_template_20261106.html','assets/field_plan_template.html')]:
        dest=OUT/target;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/source,dest)
if __name__=='__main__':main()
