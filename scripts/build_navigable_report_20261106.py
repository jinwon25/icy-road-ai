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
    assert not result['promote'] and result['new_model_fits']==20 and audit['status']=='short_forcing_formula_and_saved_scores_verified'
    candidate=result['reports']['candidate']['1'];baseline=result['reports']['physical']['1']
    s=(ROOT/'scripts/build_jury_report_20261106.py').read_text('utf8')
    s=swap(s,"P=ROOT/'outputs/private';B=P/'final_jury_review_20261106/icy_road_model';W=P/'final_jury_review_20261106';O=B/'report';F=O/'figures'",
        "P=ROOT/'outputs/private';B=P/'late_research_design_20261106/icy_road_model';W=P/'late_research_design_20261106';O=B/'report';F=O/'figures'")
    s=swap(s," page('자료와 분석 방법')",""" h('질문별로 읽기')
 table([['온도 추정의 비교 근거','결빙 판정과 오경보','목록 대조와 현장 확인'],['3-4쪽','6-7쪽','10-13쪽']],[169,169,169])
 p('결빙의 날짜별 평균 정밀도는 1.95%다. 온도 추정의 개선과 실제 Ice 판정의 한계를 구분해 읽어야 한다.',small)
 page('자료와 분석 방법')""")
    old=" p('따라서 다음 공간 결과의 저온·수분 조건 비율은 실제 결빙 확률로 해석하지 않았다. 관측 공백과 도로환경을 함께 살펴, 직접 계측과 현장 확인이 필요한 범위를 선정하는 데 사용했다.')"
    paragraph=f"짧은 기상 이력도 추가 검토했다. 최근 국내 연구[13]의 감쇠 누적을 참고해 ASOS 기온·지면온도 대리 입력으로 20개 지역 제외 분류기를 학습했다. 내부 문턱 선택 후 지역 제외 F1은 {candidate['f1']:.4f}로 고정 물리 기준 {baseline['f1']:.4f}보다 낮아 채택하지 않았다. 실제 노면 관측을 사용하는 선행연구의 미래 결빙 시작 예측과는 입력·목표가 다르다."
    s=swap(s,old," p("+repr(paragraph)+",small)\n"+old)
    old=" ('[12] Nlenanya et al. Standardized Framework for Winter Weather Road Condition Indices. Aurora (2026).','https://www.intrans.iastate.edu/wp-content/uploads/2026/03/standardized_framework_road_condition_indices_w_cvr.pdf')]"
    s=swap(s,old,old[:-1]+",\n ('[13] Yi & Seo. Early warning of road icing from antecedent meteorological conditions without consistent critical slowing down. arXiv:2609.33528 (2026), 사전 공개 논문.','https://arxiv.org/abs/2609.33528')]")
    generated=ROOT/'scripts/render_navigable_report_body_20261106.py';assert not generated.exists();generated.write_text(s,'utf8')
    pdf=B/'report/analysis_report.pdf';original=W/'report_before_navigation.pdf'
    assert pdf.resolve().is_relative_to(W.resolve()) and not original.exists();pdf.rename(original)
    r=subprocess.run([sys.executable,'-X','utf8',str(generated)],cwd=ROOT,env=dict(os.environ),capture_output=True,text=True,encoding='utf8',timeout=180)
    assert r.returncode==0,r.stdout+r.stderr
    doc=fitz.open(pdf);assert len(doc)==14
    titles=['결과 요약','자료와 분석 방법','학습에서 제외한 지점의 노면온도','비교 기준으로 확인한 노면온도 추정의 가치','도로 기상 추정','결빙 판정의 성능과 오경보','영하·적설 조건과 실제 결빙 사이의 차이','기상요소와 결빙 조건의 관계','겨울별 조건 노출과 도로환경','공개 목록과 기상 기준의 관계','추가 계측·시설 확인 범위','선정 기준을 바꾸면 남는 구간','지형에서 확인할 낮의 일사 환경','활용 범위와 결론']
    doc.set_toc([[1,title,i+1] for i,title in enumerate(titles)])
    links=[]
    for label,page in [('3-4쪽',2),('6-7쪽',5),('10-13쪽',9)]:
        rects=doc[0].search_for(label);assert len(rects)==1,(label,rects)
        rect=rects[0]+(-5,-4,5,4)
        doc[0].insert_link({'kind':fitz.LINK_GOTO,'from':rect,'page':page,'to':fitz.Point(0,0)})
        links.append(dict(label=label,destination_page=page+1))
    temp=B/'report/report_with_navigation.pdf';assert not temp.exists();doc.save(temp,garbage=4,deflate=True);doc.close()
    unlinked=W/'report_before_bookmarks.pdf';assert not unlinked.exists();pdf.rename(unlinked);temp.rename(pdf)
    shutil.copyfile(pdf,D/'report/analysis_report.pdf')
    (D/'report/analysis_report.md').write_text((B/'report/analysis_report.md').read_text('utf8').replace('](figures/','](../figures/'),'utf8')
    pages=W/'navigable_report_pages';pages.mkdir();doc=fitz.open(pdf);assert len(doc.get_toc())==14
    for i,page in enumerate(doc):page.get_pixmap(matrix=fitz.Matrix(1.7,1.7),alpha=False).save(pages/f'{i+1:02d}.png')
    receipt=dict(status='built_pending_visual_review',pages=14,pdf_sha256=sha(pdf),outline_entries=len(doc.get_toc()),cover_internal_links=links,reference_count=13,new_experiment_promoted=False)
    (W/'report_navigation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    print('Built 14-page report with 14 bookmarks, three cover links and new research result',flush=True)
if __name__=='__main__':main()
