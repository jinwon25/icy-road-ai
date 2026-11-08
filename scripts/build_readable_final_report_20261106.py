"""14쪽 보고서의 용어·문장·줄바꿈을 정리하고 두 단기 이력 검토를 반영한다."""
from pathlib import Path
import sys,subprocess,os
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'outputs/private/late_research_design_20261106'
def main():
    s=(ROOT/'scripts/build_navigable_report_20261106.py').read_text('utf8')
    s=s.replace("result=json.loads((E/'summary.json').read_text('utf8'));audit=json.loads((E/'audit.json').read_text('utf8'))", "result=json.loads((E/'summary.json').read_text('utf8'));audit=json.loads((E/'audit.json').read_text('utf8'))\n    aws=json.loads((P/'aws_short_forcing_icing_20261106/summary.json').read_text('utf8'));assert not aws['promote']")
    a=s.index('    paragraph=f"');b=s.index('\n    s=swap(s,old,',a)
    s=s[:a]+'''    paragraph=f"짧은 기상 이력도 추가 검토했다. 최근 국내 연구[13]의 감쇠 누적을 참고해 ASOS와 가까운 AWS의 단기 이력 후보를 각각 20회 학습했다. 내부에서 모형과 문턱을 고른 뒤 지역을 바꿔 시험한 F1은 각각 {candidate['f1']:.4f}·{aws['reports']['candidate']['1']['f1']:.4f}로, 고정 물리 기준 {baseline['f1']:.4f}보다 낮아 채택하지 않았다. 원 연구는 실제 노면 관측으로 미래의 결빙 시작을 예측하므로 우리 입력·목표와 다르다."
'''+s[b:]
    marker="    generated=ROOT/'scripts/render_navigable_report_body_20261106.py'"
    assert marker in s
    changes={
      "학습에서 제외한 지점의 노면온도":"학습에 쓰지 않은 지점의 온도 오차",
      "비교 기준으로 확인한 노면온도 추정의 가치":"같은 자료로 비교한 노면온도 오차",
      "도로 기상 추정":"도로의 기온·습도·풍속 추정",
      "결빙 판정의 성능과 오경보":"결빙 판정에서 맞힌 경우와 놓친 경우",
      "영하·적설 조건과 실제 결빙 사이의 차이":"추운 날씨와 실제 도로 결빙은 달랐다",
      "기상요소와 결빙 조건의 관계":"어떤 기상 조건에서 판정이 늘었는가",
      "겨울별 조건 노출과 도로환경":"두 겨울의 저온·수분 조건과 도로환경",
      "공개 목록과 기상 기준의 관계":"기존 취약구간과 우리 기준의 비교",
      "추가 계측·시설 확인 범위":"추가로 관측하고 현장을 확인할 두 범위",
      "선정 기준을 바꾸면 남는 구간":"기준을 바꿔도 남는 구간은 어디인가",
      "지형에서 확인할 낮의 일사 환경":"지형 때문에 햇빛이 가려질 수 있는 시간",
      "활용 범위와 결론":"활용할 수 있는 범위와 남은 확인",
      "질문별로 읽기":"궁금한 부분부터 읽기",
      "wordWrap='CJK'":"wordWrap=None",
      "공통 관측쌍":"같은 시각의 공통 자료",
      "구간별 노출 비율":"구간별 저온·수분 조건 비율",
      "구간 노출의 분위수에는":"구간의 상위 조건을 고를 때는",
      "노면온도 MAE 평균":"노면온도 평균 절대오차(MAE)",
      "학습에서 제외한 3지점":"학습에 쓰지 않은 3지점",
    }
    insert="    for a,b in "+repr(changes)+".items():s=s.replace(a,b)\n"
    old="부곡교·해전·삼봉의 두 겨울 관측과 동일한 10분 시각의 추정값을 비교했다. 계획 103,680시점 중 유효한 노면온도 관측·추정 쌍은 103,659개다. BIAS는 추정값에서 관측값을 뺀 값이다."
    new="부곡교·해전·삼봉의 관측온도와 같은 10분 시각의 추정온도를 비교했다. 두 값이 모두 있는 자료는 103,659개다. MAE는 두 온도의 차이에서 부호를 없애고 평균한 값이다. BIAS는 추정값-관측값의 평균으로, 낮게 또는 높게 추정하는 경향을 보여준다."
    insert+="    s=s.replace("+repr(old)+","+repr(new)+")\n"
    old="Precision·Recall·F1은 날짜별로 계산한 뒤 지점별 기간 평균과 지점 평균을 구했다."
    new="정밀도(Precision)는 결빙 판정 중 실제 Ice의 비율, 재현율(Recall)은 실제 Ice 중 잡아낸 비율이다. F1은 두 지표를 함께 본다. 각 지표를 날짜별로 계산하고 지점별 기간 평균과 지점 평균을 구했다."
    insert+="    s=s.replace("+repr(old)+","+repr(new)+")\n"
    old="노면수분·염분·제설·마찰 자료를 확보하고 오경보와 미탐의 비용을 정해 판정 기준을 검증할 필요가 있다."
    new="노면수분·염분·제설·마찰 자료를 확보하고, 잘못 알리는 경우와 놓치는 경우의 비용을 정해 판정 기준을 검증해야 한다. 상용 노면센서도 온도와 수분·제빙재를 함께 측정한다[14]."
    insert+="    s=s.replace("+repr(old)+","+repr(new)+")\n"
    old="사전 공개 논문.','https://arxiv.org/abs/2609.33528')]"
    new="사전 공개 논문.','https://arxiv.org/abs/2609.33528'),\\n ('[14] Vaisala. Road Sensor DRS511. 온도·노면수분·제빙재 측정 항목.','https://www.vaisala.com/en/products/weather-environmental-sensors/road-sensor-drs511')]"
    insert+="    s=s.replace("+repr(old)+","+repr(new.replace('\\n','\n'))+")\n"
    insert+="    s=s.replace(\" h('궁금한 부분부터 읽기')\",\" h('궁금한 부분부터 읽기')\\n p('쪽 번호를 누르면 해당 부분으로 이동한다.',small)\")\n"
    s=s.replace(marker,insert+marker)
    # Match bookmark names with the revised page headings as well.
    for old,new in changes.items():
        if old not in ['wordWrap=\'CJK\'','공통 관측쌍','구간별 노출 비율','구간 노출의 분위수에는','노면온도 MAE 평균','학습에서 제외한 3지점']:s=s.replace(old,new)
    s=s.replace('render_navigable_report_body_20261106.py','render_readable_final_report_body_20261106.py').replace('report_before_navigation.pdf','report_before_plain_language.pdf').replace('report_before_bookmarks.pdf','report_before_final_bookmarks.pdf').replace("W/'navigable_report_pages'","W/'plain_language_report_pages'")
    s=s.replace('reference_count=13','reference_count=14')
    s=s.replace("links.append(dict(label=label,destination_page=page+1))","doc[0].draw_line(fitz.Point(rect.x0+5,rect.y1-3),fitz.Point(rect.x1-5,rect.y1-3),color=(.16,.33,.43),width=.5)\n        links.append(dict(label=label,destination_page=page+1))")
    p=ROOT/'scripts/render_readable_final_report_20261106.py';assert not p.exists();p.write_text(s,'utf8')
    record=W/'report_build.json';archive=W/'report_build_before_plain_language.json'
    assert record.resolve().is_relative_to(W.resolve()) and not archive.exists();record.rename(archive)
    r=subprocess.run([sys.executable,'-X','utf8',str(p)],cwd=ROOT,env=dict(os.environ),capture_output=True,text=True,encoding='utf8',timeout=180)
    assert r.returncode==0,r.stdout+r.stderr
    print(r.stdout.strip(),flush=True)
if __name__=='__main__':main()
