"""추가 검토 결과와 질문별 이동을 반영하고 PDF 전체 쪽을 렌더한다."""
from pathlib import Path
import sys,json,re,shutil,subprocess,os
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
P=ROOT/'outputs/private';W=P/'late_research_design_20261106';B=W/'icy_road_model';D=W/'icy_road_documents';E=P/'short_forcing_icing_20261106'
def swap(s,a,b):assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
def main():
    result=json.loads((E/'summary.json').read_text('utf8'));audit=json.loads((E/'audit.json').read_text('utf8'))
    aws=json.loads((P/'aws_short_forcing_icing_20261106/summary.json').read_text('utf8'));assert not aws['promote']
    assert not result['promote'] and result['new_model_fits']==20 and audit['status']=='short_forcing_formula_and_saved_scores_verified'
    candidate=result['reports']['candidate']['1'];baseline=result['reports']['physical']['1']
    s=(ROOT/'scripts/build_jury_report_20261106.py').read_text('utf8')
    s=swap(s,"P=ROOT/'outputs/private';B=P/'final_jury_review_20261106/icy_road_model';W=P/'final_jury_review_20261106';O=B/'report';F=O/'figures'",
        "P=ROOT/'outputs/private';B=P/'late_research_design_20261106/icy_road_model';W=P/'late_research_design_20261106';O=B/'report';F=O/'figures'")
    s=swap(s," page('자료와 분석 방법')",""" h('궁금한 부분부터 읽기')
 table([['온도 추정의 비교 근거','결빙 판정과 오경보','목록 대조와 현장 확인'],['3-4쪽','6-7쪽','10-13쪽']],[169,169,169])
 p('결빙의 날짜별 평균 정밀도는 1.95%다. 온도 추정의 개선과 실제 Ice 판정의 한계를 구분해 읽어야 한다.',small)
 page('자료와 분석 방법')""")
    old=" p('따라서 다음 공간 결과의 저온·수분 조건 비율은 실제 결빙 확률로 해석하지 않았다. 관측 공백과 도로환경을 함께 살펴, 직접 계측과 현장 확인이 필요한 범위를 선정하는 데 사용했다.')"
    paragraph=f"짧은 기상 이력도 추가 검토했다. 최근 국내 연구[13]의 감쇠 누적을 참고해 ASOS와 가까운 AWS의 단기 이력 후보를 각각 20회 학습했다. 내부에서 모형과 문턱을 고른 뒤 지역을 바꿔 시험한 F1은 각각 {candidate['f1']:.4f}·{aws['reports']['candidate']['1']['f1']:.4f}로, 고정 물리 기준 {baseline['f1']:.4f}보다 낮아 채택하지 않았다. 원 연구는 실제 노면 관측으로 미래의 결빙 시작을 예측하므로 우리 입력·목표와 다르다."

    s=swap(s,old," p("+repr(paragraph)+",small)\n"+old)
    old=" ('[12] Nlenanya et al. Standardized Framework for Winter Weather Road Condition Indices. Aurora (2026).','https://www.intrans.iastate.edu/wp-content/uploads/2026/03/standardized_framework_road_condition_indices_w_cvr.pdf')]"
    s=swap(s,old,old[:-1]+",\n ('[13] Yi & Seo. Early warning of road icing from antecedent meteorological conditions without consistent critical slowing down. arXiv:2609.33528 (2026), 사전 공개 논문.','https://arxiv.org/abs/2609.33528')]")
    for a,b in {'학습에 쓰지 않은 지점의 온도 오차': '학습에 쓰지 않은 지점의 온도 오차', '같은 자료로 비교한 노면온도 오차': '같은 자료로 비교한 노면온도 오차', '도로의 기온·습도·풍속 추정': '도로의 기온·습도·풍속 추정', '결빙 판정에서 맞힌 경우와 놓친 경우': '결빙 판정에서 맞힌 경우와 놓친 경우', '추운 날씨와 실제 도로 결빙은 달랐다': '추운 날씨와 실제 도로 결빙은 달랐다', '어떤 기상 조건에서 판정이 늘었는가': '어떤 기상 조건에서 판정이 늘었는가', '두 겨울의 저온·수분 조건과 도로환경': '두 겨울의 저온·수분 조건과 도로환경', '기존 취약구간과 우리 기준의 비교': '기존 취약구간과 우리 기준의 비교', '추가로 관측하고 현장을 확인할 두 범위': '추가로 관측하고 현장을 확인할 두 범위', '기준을 바꿔도 남는 구간은 어디인가': '기준을 바꿔도 남는 구간은 어디인가', '지형 때문에 햇빛이 가려질 수 있는 시간': '지형 때문에 햇빛이 가려질 수 있는 시간', '활용할 수 있는 범위와 남은 확인': '활용할 수 있는 범위와 남은 확인', '궁금한 부분부터 읽기': '궁금한 부분부터 읽기', "wordWrap='CJK'": 'wordWrap=None', '공통 관측쌍': '같은 시각의 공통 자료', '구간별 노출 비율': '구간별 저온·수분 조건 비율', '구간 노출의 분위수에는': '구간의 상위 조건을 고를 때는', '노면온도 MAE 평균': '노면온도 평균 절대오차(MAE)', '학습에서 제외한 3지점': '학습에 쓰지 않은 3지점'}.items():s=s.replace(a,b)
    s=s.replace('부곡교·해전·삼봉의 두 겨울 관측과 동일한 10분 시각의 추정값을 비교했다. 계획 103,680시점 중 유효한 노면온도 관측·추정 쌍은 103,659개다. BIAS는 추정값에서 관측값을 뺀 값이다.','부곡교·해전·삼봉의 관측온도와 같은 10분 시각의 추정온도를 비교했다. 두 값이 모두 있는 자료는 103,659개다. MAE는 두 온도의 차이에서 부호를 없애고 평균한 값이다. BIAS는 추정값-관측값의 평균으로, 낮게 또는 높게 추정하는 경향을 보여준다.')
    s=s.replace('Precision·Recall·F1은 날짜별로 계산한 뒤 지점별 기간 평균과 지점 평균을 구했다.','정밀도(Precision)는 결빙 판정 중 실제 Ice의 비율, 재현율(Recall)은 실제 Ice 중 잡아낸 비율이다. F1은 두 지표를 함께 본다. 각 지표를 날짜별로 계산하고 지점별 기간 평균과 지점 평균을 구했다.')
    s=s.replace('노면수분·염분·제설·마찰 자료를 확보하고 오경보와 미탐의 비용을 정해 판정 기준을 검증할 필요가 있다.','노면수분·염분·제설·마찰 자료를 확보하고, 잘못 알리는 경우와 놓치는 경우의 비용을 정해 판정 기준을 검증해야 한다. 상용 노면센서도 온도와 수분·제빙재를 함께 측정한다[14].')
    s=s.replace("사전 공개 논문.','https://arxiv.org/abs/2609.33528')]","사전 공개 논문.','https://arxiv.org/abs/2609.33528'),\n ('[14] Vaisala. Road Sensor DRS511. 온도·노면수분·제빙재 측정 항목.','https://www.vaisala.com/en/products/weather-environmental-sensors/road-sensor-drs511')]")
    s=s.replace(" h('궁금한 부분부터 읽기')"," h('궁금한 부분부터 읽기')\n p('쪽 번호를 누르면 해당 부분으로 이동한다.',small)")
    generated=ROOT/'scripts/render_readable_final_report_body_20261106.py';assert not generated.exists();generated.write_text(s,'utf8')
    pdf=B/'report/analysis_report.pdf';original=W/'report_before_plain_language.pdf'
    assert pdf.resolve().is_relative_to(W.resolve()) and not original.exists();pdf.rename(original)
    r=subprocess.run([sys.executable,'-X','utf8',str(generated)],cwd=ROOT,env=dict(os.environ),capture_output=True,text=True,encoding='utf8',timeout=180)
    assert r.returncode==0,r.stdout+r.stderr
    doc=fitz.open(pdf);assert len(doc)==14
    titles=['결과 요약','자료와 분석 방법','학습에 쓰지 않은 지점의 온도 오차','같은 자료로 비교한 노면온도 오차','도로의 기온·습도·풍속 추정','결빙 판정에서 맞힌 경우와 놓친 경우','추운 날씨와 실제 도로 결빙은 달랐다','어떤 기상 조건에서 판정이 늘었는가','두 겨울의 저온·수분 조건과 도로환경','기존 취약구간과 우리 기준의 비교','추가로 관측하고 현장을 확인할 두 범위','기준을 바꿔도 남는 구간은 어디인가','지형 때문에 햇빛이 가려질 수 있는 시간','활용할 수 있는 범위와 남은 확인']
    doc.set_toc([[1,title,i+1] for i,title in enumerate(titles)])
    links=[]
    for label,page in [('3-4쪽',2),('6-7쪽',5),('10-13쪽',9)]:
        rects=doc[0].search_for(label);assert len(rects)==1,(label,rects)
        rect=rects[0]+(-5,-4,5,4)
        doc[0].insert_link({'kind':fitz.LINK_GOTO,'from':rect,'page':page,'to':fitz.Point(0,0)})
        doc[0].draw_line(fitz.Point(rect.x0+5,rect.y1-3),fitz.Point(rect.x1-5,rect.y1-3),color=(.16,.33,.43),width=.5)
        links.append(dict(label=label,destination_page=page+1))
    temp=B/'report/report_with_navigation.pdf';assert not temp.exists();doc.save(temp,garbage=4,deflate=True);doc.close()
    unlinked=W/'report_before_final_bookmarks.pdf';assert not unlinked.exists();pdf.rename(unlinked);temp.rename(pdf)
    shutil.copyfile(pdf,D/'report/analysis_report.pdf')
    (D/'report/analysis_report.md').write_text((B/'report/analysis_report.md').read_text('utf8').replace('](figures/','](../figures/'),'utf8')
    pages=W/'plain_language_report_pages';pages.mkdir();doc=fitz.open(pdf);assert len(doc.get_toc())==14
    for i,page in enumerate(doc):page.get_pixmap(matrix=fitz.Matrix(1.7,1.7),alpha=False).save(pages/f'{i+1:02d}.png')
    receipt=dict(status='built_pending_visual_review',pages=14,pdf_sha256=sha(pdf),outline_entries=len(doc.get_toc()),cover_internal_links=links,reference_count=14,new_experiment_promoted=False)
    (W/'report_navigation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    print('Built 14-page report with 14 bookmarks, three cover links and new research result',flush=True)
if __name__=='__main__':main()
