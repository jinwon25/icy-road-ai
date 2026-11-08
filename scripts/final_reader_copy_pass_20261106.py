"""화면 방향에 의존하는 문구와 그림 비율·기준선 명칭을 최종 정리한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];B=ROOT/'outputs/private/late_research_design_20261106/icy_road_model'
def main():
    p=B/'demo/index.html';s=p.read_text('utf8')
    assert '왼쪽 값은 날짜별 지표의 평균입니다.' in s
    s=s.replace('왼쪽 값은 날짜별 지표의 평균입니다.','각 지표는 날짜별 값의 평균입니다.')
    s=s.replace("'가까운 AWS 기온'","'AWS 기온 우선'")
    s=s.replace('<p class="plot-caption">오차가 작을수록 관측온도에 가깝습니다.</p>',
        '<p class="plot-caption">오차가 작을수록 관측온도에 가깝습니다. AWS 기온을 이용할 수 없을 때는 ASOS로 보완한 기준입니다.</p>')
    s=s.replace('<img src="poster.png" alt=', '<img src="poster.png" width="1440" height="1080" fetchpriority="high" alt=')
    s=s.replace('width="900" height="320" loading="lazy"','width="1164" height="507" loading="lazy"')
    p.write_text(s,'utf8')
if __name__=='__main__':main()
