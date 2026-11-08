"""미채택 비교의 수치와 재집계 코드를 제출 설명에 정직하게 반영한다."""
from pathlib import Path
import json,shutil,sys,subprocess
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'outputs/private/evening_refinement_20261106';B=W/'icy_road_model';D=W/'icy_road_documents'
E=ROOT/'outputs/private/fixed_temperature_icing_20261106'
def main():
    summary=json.loads((E/'summary.json').read_text('utf8'));assert not summary['passed_candidates']
    target=B/'results/evaluation/fixed_temperature_rule_review';target.mkdir()
    for name in ['comparison.csv','summary.json','plan.json']:shutil.copyfile(E/name,target/name)
    p=pd.read_parquet(E/'predictions.parquet')
    p[['station','time','prediction']].to_parquet(target/'temperature_cross_region.parquet',index=False,compression='zstd')
    shutil.copyfile(ROOT/'scripts/fixed_temperature_comparison_runtime_20261106.py',B/'code/compare_fixed_temperature_rules.py')
    a=B/'AI_USAGE.md';text=a.read_text('utf8')
    text+='''
## 온도 정확도와 결빙 판정의 추가 대조

기존 지역 제외 예측을 이용해, 결빙 조건의 기준온도를 63특성 노면온도로 바꾸는 규칙과 기존·새 온도 조건을 함께 요구하는 규칙을 사전 고정해 비교했다. 새 학습이나 문턱 탐색은 하지 않았다. 개발 9지점의 같은 309,928개 유효쌍에서 온도 교체는 오경보를 826건 늘렸다. 두 조건의 동시 충족은 오경보를 940건 줄였지만 실제 Ice 54시점과 기존에 검출한 10개 사건을 더 놓쳤다. 날짜 블록 민감도에서도 F1 개선이 안정적이지 않아 제출 판정에 채택하지 않았다.

[공통 쌍의 비교 표](results/evaluation/fixed_temperature_rule_review/comparison.csv)와 포함 예측으로 재집계하는 코드를 제공한다. 반복 사용한 개발 지역의 고정 규칙 비교이며 새로운 독립 평가로 해석하지 않는다. 보호 지점이나 외부 보류 지점의 정답은 이 비교에 사용하지 않았다.
'''
    a.write_text(text,'utf8')
    # 문서자료는 모델자료 내부 상대 경로 대신 함께 제공하는 원표를 가리킨다.
    shutil.copyfile(target/'comparison.csv',D/'data/fixed_temperature_rule_comparison.csv')
    (D/'AI_USAGE.md').write_text(text.replace('results/evaluation/fixed_temperature_rule_review/comparison.csv','data/fixed_temperature_rule_comparison.csv'),'utf8')
    readme=B/'README.md';text=readme.read_text('utf8')
    text=text.replace('    python code/analyze_icing_errors.py --output local_review/icing_error_analysis',
        '    python code/analyze_icing_errors.py --output local_review/icing_error_analysis\n    python code/compare_fixed_temperature_rules.py --output local_review/fixed_temperature_rules')
    readme.write_text(text,'utf8')
    subprocess.run([sys.executable,'-X','utf8',str(B/'code/compare_fixed_temperature_rules.py'),'--output',str(B/'local_review/fixed_rule_reproduction')],check=True)
if __name__=='__main__':main()
