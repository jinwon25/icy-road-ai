"""새 관측망 비교·입력 점검을 수치 대조하고 v11의 22쪽에 2쪽을 덧붙인다."""
import argparse
import html
from pathlib import Path
import sys

import fitz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from markdown_it import MarkdownIt
import pandas as pd
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image,PageBreak,Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_objective_icing import read,write,now,verify_preserved
from scripts.build_editorial_report import inline
from src.data_source import sha256_file as sha

P=ROOT/'outputs/private';STUDY=P/'weather_network_20261101_v1'
OUT=P/'network_followup_review_20261101_v1'
REPORT=P/'report_update_20261101_v12'
OLD=P/'report_update_20261101_v11_final/analysis_report_v11.pdf'
MANUSCRIPT=ROOT/'docs/delivery/ANALYSIS_REPORT_V12_20261101.md'
APPENDIX=ROOT/'docs/delivery/WEATHER_NETWORK_APPENDIX_20261101.md'
TARGETS={'air_temperature':('기온','°C'),'relative_humidity':('상대습도','%p'),'wind_speed':('풍속','m/s')}
QA=P/'weather_network_viewer_qa_20261101_v3'


def evidence():
    s=read(STUDY/'summary.json');a=read(STUDY/'independent_verification.json')
    assert a['status']=='passed' and a['summary_sha256']==sha(STUDY/'summary.json')
    assert s['accepted_targets']==['wind_speed']
    wind=read(P/'wind_network_supplement_validation_20261101_v1/receipt.json')
    assert wind['status']=='wind_network_supplement_verified' and wind['refit_rows_exact']==432
    assert len(s['fits'])==36
    assert read(QA/'visual_review.json')['status']=='passed'
    assert sha(OLD)=='d8e9ca261265a011fe01d198a0a3a609c6818f0b1cd569906158a59e0b041f53'
    return s,a


def prepare():
    if OUT.exists() or APPENDIX.exists() or MANUSCRIPT.exists():raise FileExistsError('Preserve prepared report')
    s,a=evidence();OUT.mkdir();rows=[]
    for target,modes in s['reports'].items():
        for mode,result in modes.items():
            for candidate,metrics in result['metrics'].items():
                rows.append(dict(target=target,mode=mode,candidate=candidate,**metrics['pooled']))
    table=pd.DataFrame(rows);table.to_csv(OUT/'comparison_metrics.csv',index=False,encoding='utf-8-sig')
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
    fig,axes=plt.subplots(1,3,figsize=(11,3.4))
    for ax,(target,(label,unit)) in zip(axes,TARGETS.items()):
        for j,(candidate,name,color) in enumerate([('current','기존 모형','#294b63'),('network_residual','관측망 추가','#18858a')]):
            values=[s['reports'][target][mode]['metrics'][candidate]['pooled']['mae'] for mode in ['spatial','joint']]
            ax.bar([-.18+j*.36,.82+j*.36],values,.34,label=name,color=color)
            for x,value in zip([-.18+j*.36,.82+j*.36],values):ax.text(x,value+.015*max(values),f'{value:.3f}',ha='center',va='bottom',fontsize=9)
        ax.set_xticks([0,1],['지역 제외','지역·겨울 제외']);ax.set_title(label+' MAE ('+unit+')');ax.set_ylim(0,ax.get_ylim()[1]*1.12)
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.spines[['top','right']].set_visible(False)
    axes[0].legend(loc='upper left',fontsize=9);fig.tight_layout();fig.savefig(ROOT/'docs/images/weather_network_comparison_20261101.png',dpi=160,bbox_inches='tight');plt.close(fig)
    with PILImage.open(QA/'desktop.png') as im:im.crop((100,230,1280,900)).save(ROOT/'docs/images/weather_network_audit_20261101.png')
    lines=[]
    for target,(label,unit) in TARGETS.items():
        for mode in ['spatial','joint']:
            r=s['reports'][target][mode];b=r['metrics']['current']['pooled']['mae'];c=r['metrics']['network_residual']['pooled']['mae']
            decision='채택' if target=='wind_speed' else '미채택'
            lines.append(f"| {label}·{'지역' if mode=='spatial' else '지역+겨울'} ({unit}) | {b:.6f} | {c:.6f} | {decision} |")
    first='''## 13. 주변 AWS 관측망으로 풍속 추정을 추가 개선했다

최근접 관측소에 의존하는 입력에 새로운 공간 정보를 추가했다. 50km 안 가까운 AWS 최대 4곳의 엄격한 과거 15분 관측을 거리 제곱 역수로 결합했다. 기온·습도·풍속·15분 강수·이슬점 각각의 평균·표준편차·범위·현재 AWS와 차이·개수·가중 거리·유효 개수, 총 35특성을 더했다. 미터 단위가 불명확한 대회 DEM을 역정규화하거나 관측 높이·일정한 고도감률을 가정하지 않았다.

openAMUNDSEN [1]의 거리 가중 보간과 결측 처리, 시간별 복합지형 보간 [2], 2026년 일기온 잔차 보간 [3]을 대조했다. 원 연구의 고도 추세·공분산 모형·성능 수치를 가져오지 않았다. 공개 구현 [4]은 읽기만 했고 실행하거나 모델·자료를 가져오지 않았다.

기온·풍속 34특성, 현재 습도 82특성에 각각 35개를 추가했다. 모형 설정·평가 분모는 유지했다. 3목표×(지역 4회+지역·겨울 8회)=36개를 적합했고, 현재 저장 모형과 단순 IDW를 같은 행에서 비교했다.

| 대상·검증 | 기존 MAE | 관측망 MAE | 판단 |
| --- | ---: | ---: | --- |
'''+ '\n'.join(lines)+'''

![그림 7. 같은 개발 자료에서 현재 모형과 주변 관측망 추가의 MAE. 지표가 낮을수록 좋지만 지역·겨울별 제약도 함께 평가했다.](../images/weather_network_comparison_20261101.png)

목표별 두 검증 모두 전체 2% 이상 개선, 각 겨울 비악화, 각 지역 악화 10% 이내, 저온 비악화, 날짜 블록 차이 상한 0 미만을 요구했다. 풍속만 두 검증의 모든 조건을 통과했다. 지역 MAE는11.27%, 지역·겨울은10.41% 추가 감소했다. 기온·습도는 유지한다. 같은 개발 지역의 반복 비교이며 새로운 독립 평가나 공식 성적이 아니다.
'''
    second='''## 14. 입력의 출처·지연·결측을 도로별로 검토한다

도로 23곳과 AWS 34곳의 연결을 보는 별도 오프라인 화면을 추가했다. 두 겨울에서 고정한 16예시 시각과 5변수를 선택하면 원 관측 시각·거리·관측 나이·변수별 유효 가중치가 표시된다. 실제 도로 기상·노면온도·결빙 정답은 포함하지 않았다.

![그림 8. 실제 관측망 점검 화면. 관측소 간 상대습도 범위 41.30%p는 입력 간 차이이며 추정 오차나 예측구간이 아니다.](../images/weather_network_audit_20261101.png)

전체 입력 달력의 두 겨울 평균 유효 관측소 수·유효 개수·가중 거리·관측소 범위를 도로별로 확인하고, 선택 원천·전체 품질 CSV를 내려받는다. 화면의 16예시를 전체 시계열 검증으로 확대하지 않는다. 기존 843구간·240일 기상 탐색과 함께 사용한다.

'''+f"별도 merge_asof로 공간 입력 {a['feature_values_checked']:,}개 값을 재계산했고, 저장 예측 {a['predictions_checked']:,}개·지표 {a['metric_checks']:,}건과 대표 6모형의 정확한 재학습을 확인했다. 화면은 1,472원천행·12,880표시값·1,840선택조합·실제 SVG선택·4행 CSV·390px 모바일을 검증했다. 외부 요청과 JavaScript 오류는 0이다.\n\n"+'''
새 풍속은 허용13기상 지점의 두 겨울 전체로 학습한 독립 실행 묶음이다. 별도 위치에서 API·실제 CLI·전체 재학습의432행 일치를 확인했다. 전체 과거와 예제 원천 문맥도 정확히 같다. 기존843구간 풍속 지도는 앞선 모형 결과로 보존하며 이 새 모형 적용 지도로 표시하지 않는다. 기존 기온·습도·노면온도·결빙은 바꾸지 않는다.

대회 자산 없는 저장소 사본의 실행 검사와 Git 이력1,120개 파일 내용의 실제 키·토큰 검사를 수행했다. 키 검출은0이었다. 이는 데이터 없는 학습 전체 재현을 뜻하지 않는다. 원자료·모형·예측·신청서·인증정보는 비공개 GitHub에도 올리지 않는다.

참고: [1] [openAMUNDSEN v1.0](https://gmd.copernicus.org/articles/17/6775/2024/) 및 [공식 처리 문서](https://doc.openamundsen.org/des/meteo). [2] [Frey & Frei (2025), 시간별 기온 보간](https://rmets.onlinelibrary.wiley.com/doi/full/10.1002/joc.8796). [3] [Zhejiang 일기온 잔차 보간 (2026)](https://link.springer.com/article/10.1007/s00704-026-06521-3). [4] [공개 코드 고정 버전](https://github.com/openamundsen/openamundsen/blob/fb65b34ca24829ceaa3ea7e7930535c129461048/openamundsen/interpolation.py), MIT.
'''
    appendix=first+'\n<!-- page -->\n\n'+second
    APPENDIX.write_text(appendix,'utf8')
    old=(ROOT/'docs/delivery/ANALYSIS_REPORT_V11_20261101.md').read_text('utf8')
    before,after=old.split('<!-- page -->',1)
    before=before.replace('22.10·12.91·42.67%', '22.10·12.91·49.13%')
    before=before.replace('온도·습도 추정의 개선은 확인되었지만', '풍속은 주변 AWS를 추가해 지역 MAE0.563455→0.499955m/s(11.27%), 지역·겨울 MAE0.567465→0.508379m/s(10.41%)로 더 낮췄다. 온도·습도·풍속 추정의 개선은 확인되었지만')
    before+='\n**최신 풍속.** 뒤의13·14장 추가 검토에서69특성 모형과 독립 실행·전체 재학습을 확인한다. 기존 본문의34특성 풍속 수치와843구간 풍속 지도는 이전 버전의 근거로 보존한다.\n\n'
    old=before+'<!-- page -->'+after
    MANUSCRIPT.write_text(old+'\n<!-- page -->\n\n'+appendix,'utf8')
    research='# AWS 관측망 정보의 통제 비교와 입력 점검\n\n2026-11-01. 풍속 MAE를 지역 제외0.563455→0.499955m/s(11.27% 추가 감소), 지역·겨울 동시 제외0.567465→0.508379m/s(10.41%)로 개선했습니다. 별도 실행·전체 재학습을 검증했으며 기존 기온·습도·노면온도·결빙과843구간 지도는 보존합니다.\n\n'+appendix.replace('<!-- page -->','')
    (ROOT/'docs/research/WEATHER_NETWORK_20261101.md').write_text(research,'utf8')
    write(OUT/'preparation.json',dict(status='prepared',at_utc=now(),metrics_rows=len(table),study_summary_sha256=sha(STUDY/'summary.json'),
        study_audit_sha256=sha(STUDY/'independent_verification.json'),appendix_sha256=sha(APPENDIX),manuscript_sha256=sha(MANUSCRIPT),
        original_report_sha256=sha(OLD),protected_preservation=verify_preserved()))
    print('PREPARED',len(table),'metrics, 2 additional pages',flush=True)


def pdf():
    evidence();assert read(OUT/'preparation.json')['manuscript_sha256']==sha(MANUSCRIPT)
    if REPORT.exists():raise FileExistsError('Preserve PDF output')
    REPORT.mkdir();pdfmetrics.registerFont(TTFont('NetworkKR','C:/Windows/Fonts/malgun.ttf'));pdfmetrics.registerFont(TTFont('NetworkKRBold','C:/Windows/Fonts/malgunbd.ttf'))
    pdfmetrics.registerFontFamily('NetworkKR',normal='NetworkKR',bold='NetworkKRBold',italic='NetworkKR',boldItalic='NetworkKRBold')
    styles={n:ParagraphStyle(n,fontName='NetworkKRBold' if n=='h2' else 'NetworkKR',fontSize=size,leading=leading,wordWrap='CJK',spaceAfter=space,textColor=colors.HexColor('#20394c'))
        for n,size,leading,space in [('h2',17,24,12),('body',9.6,15.7,9),('small',8.2,12.3,6)]}
    tokens=MarkdownIt('commonmark').enable('table').parse(APPENDIX.read_text('utf8'));story=[];in_table=False;rows=[];page=1
    for i,t in enumerate(tokens):
        if t.type=='html_block':story.append(PageBreak());page+=1
        elif t.type=='heading_open':story.append(Paragraph(inline(tokens[i+1].children),styles['h2']))
        elif t.type=='table_open':in_table=True;rows=[]
        elif t.type=='tr_open':row=[]
        elif t.type=='inline' and in_table:row.append(Paragraph(inline(t.children),styles['small']))
        elif t.type=='tr_close':rows.append(row)
        elif t.type=='table_close':
            in_table=False;table=Table(rows,colWidths=[(A4[0]-88)*r for r in [.36,.23,.23,.18]],repeatRows=1)
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7f0f1')),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LINEBELOW',(0,0),(-1,-1),.25,colors.HexColor('#dce4e8')),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),4)]));story.extend([table,Spacer(1,9)])
        elif t.type=='paragraph_open' and not in_table:
            item=tokens[i+1];children=item.children or []
            if len(children)==1 and children[0].type=='image':
                image=children[0];source=(APPENDIX.parent/image.attrGet('src')).resolve()
                with PILImage.open(source) as im:w,h=im.size
                maximum=160 if 'comparison' in source.name else 230;scale=min((A4[0]-88)/w,maximum/h)
                story.extend([Image(str(source),width=w*scale,height=h*scale),Spacer(1,4),Paragraph(html.escape(image.content),styles['small'])])
            else:story.append(Paragraph(inline(children),styles['body']))
    assert page==2
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#d8e2e7'));canvas.line(44,38,A4[0]-44,38)
        canvas.setFont('NetworkKR',8);canvas.setFillColor(colors.HexColor('#607380'));canvas.drawString(44,24,'icy-road-ai · 분석 기준 2026.11.01 · 비공개 검토본');canvas.drawRightString(A4[0]-44,24,str(doc.page+22))
    extra=REPORT/'appendix.pdf';SimpleDocTemplate(str(extra),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=40,bottomMargin=50).build(story,onFirstPage=footer,onLaterPages=footer)
    from scripts.build_analysis_report_v11 import render as render_previous
    base=REPORT/'updated_base.pdf';source_text=MANUSCRIPT.read_text('utf8').rsplit('\n<!-- page -->\n\n',2)[0]
    render_previous(source_text,base)
    old=fitz.open(base);appendix=fitz.open(extra);assert len(appendix)==2,('Appendix overflow',len(appendix))
    old.insert_pdf(appendix);target=REPORT/'analysis_report_v12.pdf';old.set_metadata({'title':'미관측 고속도로의 기상·노면온도 추정과 결빙 조건','author':'icy-road-ai'});old.save(target,garbage=4,deflate=True);old.close();appendix.close()
    with fitz.open(target) as final,fitz.open(OLD) as previous:
        assert len(final)==24
        for i in range(1,22):assert final[i].get_pixmap().samples==previous[i].get_pixmap().samples
        for i,p in enumerate(final):
            for block in p.get_text('dict')['blocks']:
                if block['type']==0:
                    for line in block['lines']:
                        for span in line['spans']:
                            x0,y0,x1,y1=span['bbox'];assert x0>=39 and x1<=A4[0]-38 and y0>=33 and y1<=A4[1]-17,span['text']
            p.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(REPORT/f'page_{i+1:02}.png')
    write(REPORT/'build_receipt.json',dict(status='created_pending_visual_review',at_utc=now(),pages=24,previous_pages_pixel_identical=21,updated_abstract_pages=1,
        pdf_sha256=sha(target),manuscript_sha256=sha(MANUSCRIPT),appendix_sha256=sha(APPENDIX),sources={p.relative_to(ROOT).as_posix():sha(p)
            for p in [OLD,MANUSCRIPT,APPENDIX,Path(__file__),OUT/'preparation.json',STUDY/'summary.json',STUDY/'independent_verification.json',QA/'visual_review.json']}))
    print('PDF',target,'24 pages; abstract updated and old pages2-22 pixel-identical',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',required=True,choices=['prepare','pdf']);globals()[p.parse_args().stage]()
