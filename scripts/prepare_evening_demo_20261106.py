"""검증된 실제 탐색 영상에 현장 확인 계획을 포함하는 녹화 스크립트를 만든다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    text=(ROOT/'scripts/record_team_demo_20261106.py').read_text('utf8')
    text=text.replace("W=P/'judging_upgrade_20261106'","W=P/'evening_refinement_20261106'")
    old="  page.goto((O/'inference.html').as_uri())"
    new="""  page.goto((B/'results/field/index.html').as_uri());page.wait_for_function('window.FIELD_READY===true')
  caption('선정한 두 범위에 같은 기상 입력을 공유하는 인접 비교 후보를 연결했습니다. 실제 계측을 수행한 결과가 아니라 비교 측정 계획입니다.',5,'현장 확인 계획')
  page.locator('#S01 .area-map').scroll_into_view_if_needed()
  caption('A는 선정 범위의 대표점, B는 약 500m 떨어진 비선정 구간입니다. 위치와 선형 변화, 지형 추정을 나란히 확인합니다.',5,'같은 기상의 인접 비교')
  page.locator('#S01 summary').click();page.locator('#S01 details').scroll_into_view_if_needed()
  caption('노면온도와 실제 수분 상태, 잔류염분과 제빙 시각을 함께 기록합니다. 미측정 값은 채워 넣지 않았습니다.',5,'비교 기록 양식')
  with page.expect_download() as info:page.locator('#csv').click()
  info.value.save_as(W/'demo_unmeasured_field_record.csv')
  page.goto((O/'inference.html').as_uri())"""
    assert text.count(old)==1;text=text.replace(old,new)
    text=text.replace('기상 분포에서 계측 후보까지','지도에서 현장 확인 계획까지')
    text=text.replace('지형 맥락과 CSV 내보내기, 실제 모형 추론을 순서대로 살펴봅니다.','지형 맥락과 CSV 내보내기, 현장 확인 계획과 기록 양식, 실제 모형 추론을 순서대로 살펴봅니다.')
    text=text.replace('</nav>','<a href="../results/field/index.html">현장 확인</a></nav>')
    target=ROOT/'scripts/record_evening_demo_20261106.py';assert not target.exists();target.write_text(text,'utf8')
if __name__=='__main__':main()
