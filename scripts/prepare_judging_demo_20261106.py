"""현재 화면과 추론으로 데모를 다시 녹화할 작업 스크립트를 구성한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'outputs/private/judging_upgrade_20261106';B=W/'icy_road_model'
target=ROOT/'scripts/record_judging_demo_20261106.py';assert not target.exists()
source=(ROOT/'scripts/record_submission_demo.py').read_text('utf8')
old="P=ROOT/'outputs/private';B=P/'competition_submission/icy_road_model';W=P/'editorial_review_20261106';O=B/'demo'"
new="P=ROOT/'outputs/private';W=P/'judging_upgrade_20261106';B=W/'icy_road_model';O=B/'demo'"
assert old in source;source=source.replace(old,new)
start=source.index("  page.goto((B/'index.html').as_uri())")
end=source.index("  assert not errors and not external;video=",start)
scenes=r"""
  page.goto((B/'index.html').as_uri());page.wait_for_function('window.WEATHER_READY===true')
  caption('500m 843구간의 두 겨울 기상을 같은 척도로 비교합니다. 도로를 선택하면 일별 변화도 확인할 수 있습니다.',5,'기상 지도')
  page.select_option('#metric','2');page.select_option('#winter','1')
  caption('풍속의 지역 전체 제외 평가 MAE는 0.500m/s입니다. 각 지도 구간에서 실측 검증한 점수와는 구분합니다.',5,'풍속 추정')
  page.evaluate("document.getElementById('benchmarks').scrollIntoView({block:'start'})")
  caption('기본 12특성 회귀와 같은 관측쌍에서 비교한 노면온도 MAE가 14.6% 낮았습니다. 세 지점 모두 개선됐습니다.',7,'같은 관측쌍 비교')
  page.get_by_role('heading',name='결빙 판정과 관측 결빙일').evaluate("n=>n.scrollIntoView({block:'start'})")
  caption('결빙의 날짜별 정밀도는 0.0195로 낮습니다. 낮은 온도와 주변 적설만으로 도로 위의 Ice를 확정하기 어렵습니다.',6,'결빙 판정의 한계')
  page.goto((B/'maps/sections.html').as_uri());page.wait_for_function('window.SECTION_READY===true')
  page.locator('#criteria').evaluate('(e)=>e.open=false')
  caption('기준 조합은 22구간입니다. 각 구간의 기상·도로환경·목록 관계와 선정 근거를 함께 보여줍니다.',6,'구간별 근거')
  page.locator('#matrix').scroll_into_view_if_needed()
  caption('기상 빈도와 선형 기준, 목록 경계 여유를 바꾼 75개 조합입니다. 숫자를 누르면 그 기준을 지도에 반영합니다.',5,'기준 민감도')
  page.locator('#matrix button[data-scenario="2"]').click()
  caption('두 기준을 상위 40%로 넓히면 86구간입니다. 선정 개수는 비교 기준에 따라 달라집니다.',4,'기준 조정')
  page.evaluate("el('weatherQ').value='0.9';scenario()")
  caption('기상 상위 10%를 두 겨울 모두 요구하면 0구간입니다. 이를 도로가 안전하다는 판정으로 바꾸지 않습니다.',4,'엄격한 기준')
  page.evaluate("el('weatherQ').value='0.75';el('curveQ').value='0.75';el('margin').value='250';scenario()")
  page.locator('#area').select_option('F06');page.locator('#view').select_option('shade')
  page.locator('#map').scroll_into_view_if_needed()
  caption('F06의 두 구간은 75개 조합 중 60개에서 유지됐습니다. 공개 DSM의 지형 차폐도 현장 확인 맥락으로 제공합니다.',6,'지형 맥락')
  with page.expect_download() as info:page.locator('#download').click()
  info.value.save_as(W/'demo_selected_section.csv')
  caption('선택한 구간의 조건·기준·지형 근거를 CSV로 내려받았습니다. 실제 결빙확률이나 위험 배점으로 해석하지 않습니다.',4,'근거 내보내기')
  page.goto((O/'inference.html').as_uri())
  caption('포함된 기상 입력으로 로컬 Python 모형을 실제 실행했습니다. 예제 144행 전체가 포함된 기대 결과와 일치합니다.',7,'실제 모형 추론')
"""
source=source[:start]+scenes+source[end:]
source=source.replace('두 겨울 기상 분포, 학습 제외 지점의 노면온도, 결빙 관측일과 오경보, 추가 계측·시설 확인 범위, CSV 내보내기와 모형 추론을 순서대로 살펴봅니다.',
    '두 겨울 기상, 같은 관측쌍의 회귀 비교, 결빙 판정의 한계, 75개 기준 조합의 선택 민감도, 지형 맥락과 CSV 내보내기, 실제 모형 추론을 순서대로 살펴봅니다.')
oldvideo=B/'demo/model_demo.webm';saved=W/'original_model_demo.webm'
assert oldvideo.resolve().is_relative_to(W.resolve()) and saved.resolve().is_relative_to(W.resolve()) and not saved.exists()
oldvideo.replace(saved)
target.write_text(source,'utf8')
print('현재 화면의 실제 녹화 준비 완료')
