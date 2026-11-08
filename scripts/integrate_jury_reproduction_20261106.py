"""전체 검증 입력·재현 코드·Notebook과 과제 요구 대조표를 보완한다."""
from pathlib import Path
import json,shutil,nbformat,re
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model'
def main():
    shutil.copyfile(ROOT/'scripts/full_validation_runtime_20261106.py',B/'code/check_full_validation.py')
    source=(ROOT/'scripts/analyze_inventory_agreement_20261106.py').read_text('utf8')
    source=source.replace('import sys,json','import sys,json,argparse')
    source=source.replace('from src.data_source import sha256_file as sha','from src.evidence_hash import sha')
    source=source.replace("W=ROOT/'outputs/private/final_jury_review_20261106';B=W/'icy_road_model'","B=ROOT")
    source=source.replace('def main():','def main(output):')
    source=source.replace("out=B/'results/inventory/agreement';assert not out.exists();out.mkdir()","out=output;assert not out.exists();out.mkdir(parents=True)")
    source=source.replace('w=wind=winter.ge','w=winter.ge')
    source=source.replace("if __name__=='__main__':main()", "if __name__=='__main__':\n    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();main(a.output)")
    (B/'code/analyze_inventory_agreement.py').write_text(source,'utf8')
    nb=nbformat.read(B/'notebooks/analysis.ipynb',as_version=4)
    assert len([c for c in nb.cells if c.cell_type=='code'])==10
    nb.cells.extend([
        nbformat.v4.new_markdown_cell('## 검증 기간 전체의 실제 모델 실행\n\n정답 열이 없는 전 기간 기상 입력으로 온도·결빙을 다시 추론한다. ASOS 좌표의 태양위치와 두 겨울의 기상 이력을 포함했다. 기존 예측 103,680행과 비교하며, 관측 정답으로 모형이나 문턱을 바꾸지 않는다.'),
        nbformat.v4.new_code_cell("""review=root/'local_review';review.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='full_validation_',dir=review) as tmp:
    assert Path(tmp).resolve().is_relative_to(review.resolve())
    target=Path(tmp)/'check'
    subprocess.run([sys.executable,'-X','utf8','code/check_full_validation.py','--output',str(target)],cwd=root,env=env,check=True)
    receipt=json.loads((target/'receipt.json').read_text('utf8'))
    assert receipt['status']=='full_validation_predictions_exact' and receipt['rows']==103680
    display(pd.DataFrame([receipt]))"""),
        nbformat.v4.new_markdown_cell('## 공개 목록과 기상 기준의 관계\n\n공개 목록의 미포함 구간은 실제 비결빙 정답이 아니다. 아래 비교는 추정 이정으로 연결한 목록과 사전 고정한 기상 문턱의 관계이며, 목록을 재학습하거나 공식 지정을 바꾸지 않는다.'),
        nbformat.v4.new_code_cell("""with tempfile.TemporaryDirectory(prefix='inventory_agreement_',dir=review) as tmp:
    assert Path(tmp).resolve().is_relative_to(review.resolve())
    target=Path(tmp)/'check'
    subprocess.run([sys.executable,'-X','utf8','code/analyze_inventory_agreement.py','--output',str(target)],cwd=root,env=env,check=True)
    actual=pd.read_csv(target/'threshold_comparison.csv',float_precision='round_trip')
    expected=pd.read_csv(root/'results/inventory/agreement/threshold_comparison.csv',float_precision='round_trip')
    pd.testing.assert_frame_equal(actual,expected,check_exact=True)
    display(actual.loc[actual.source.eq('2026-09-07')&actual.margin_m.eq(250),['weather_quantile','nominal_overlap_segments','nominal_high_2024','nominal_high_2025','nominal_high_both']])""")])
    nbformat.validate(nb);nbformat.write(nb,B/'notebooks/analysis.ipynb')
    p=B/'README.md';s=p.read_text('utf8')
    needle='첫 명령은 노면온도와 결빙 조건, 둘째는 기온·습도·풍속을 산출한다.'
    addition='''검증 기간 전체를 재현하려면 다음 명령을 실행한다. 관측 정답이 없는 전용 기상 입력에 ASOS 좌표의 태양위치와 두 겨울의 이력을 포함했다. 명령은 103,680행을 다시 추론하고 온도·결빙 예측이 제출 표와 정확히 같은지 확인한다.

    python code/check_full_validation.py --output local_review/full_validation

'''
    assert s.count(needle)==1;s=s.replace(needle,addition+needle)
    needle='    python code/compare_fixed_temperature_rules.py --output local_review/fixed_temperature_rules'
    s=s.replace(needle,needle+'\n    python code/analyze_inventory_agreement.py --output local_review/inventory_agreement')
    p.write_text(s,'utf8')
    requirements=B/'technical/competition_requirements.md';s=requirements.read_text('utf8')
    s=s.replace('| 실제 탐색·추론 영상 |', '| 검증 기간 전체의 실행 재현 | ../data/validation_weather.parquet, ../code/check_full_validation.py |\n| 기존 공개 목록과 기상 문턱의 관계 | ../results/inventory/agreement/, ../code/analyze_inventory_agreement.py |\n| 실제 탐색·추론 영상 |')
    requirements.write_text(s,'utf8')
    print('전체 검증 입력·12개 실행 셀·목록 대조 재현 코드를 연결했습니다.',flush=True)
if __name__=='__main__':main()
