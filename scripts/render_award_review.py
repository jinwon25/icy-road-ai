"""수상 목표 재검토의 실제 실험·검증·해석을 6쪽 심사 검토 PDF로 만든다."""
import html
import json
from pathlib import Path
import sys
import fitz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha

def read(p):return json.loads(p.read_text('utf-8'))

def main():
    private=ROOT/'outputs/private';out=private/'award_review_20261024_v4'
    if out.exists():raise FileExistsError('Preserve rendered review')
    first=read(private/'award_ice_20261024_v1/summary.json');firstaudit=read(private/'award_ice_20261024_v1/independent_audit.json')
    two=read(private/'two_winter_models_20261024_v1/summary.json');audit=read(private/'two_winter_models_20261024_v1/audit_runtime.json')
    assert firstaudit['summary_sha256']==sha(private/'award_ice_20261024_v1/summary.json')
    assert audit['summary_sha256']==sha(private/'two_winter_models_20261024_v1/summary.json')
    inventory=pd.read_csv(private/'two_winter_development_20261024_v1/training_inventory.csv',dtype={'station':str})
    out.mkdir();plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
    fig,ax=plt.subplots(figsize=(9.4,4.4),layout='constrained')
    st=two['regression']['all']['first']['stations'];ids=list(st);y=np.arange(len(ids))
    ax.barh(y-.18,[st[s]['mae'] for s in ids],height=.33,label='첫 겨울 학습',color='#97a9bd')
    ax.barh(y+.18,[two['regression']['all']['both']['stations'][s]['mae'] for s in ids],height=.33,label='두 겨울 학습',color='#087f8c')
    ax.set_yticks(y,ids);ax.invert_yaxis();ax.set_xlabel('동일 두 겨울 공간 제외 MAE (°C)');ax.legend(loc='lower right');ax.spines[['top','right']].set_visible(False)
    fig.savefig(out/'temperature.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9.4,4.3),layout='constrained')
    inv=inventory.pivot(index='station',columns='winter',values='ice_slots');y=np.arange(len(inv))
    ax.bar(y-.18,inv[2024],width=.35,label='2024/25',color='#b2bccb');ax.bar(y+.18,inv[2025],width=.35,label='2025/26',color='#087f8c')
    ax.set_yscale('symlog',linthresh=1);ax.set_xticks(y,inv.index,rotation=70);ax.set_ylabel('관측 Ice 슬롯 수 (0 포함 대칭 로그축)');ax.legend();ax.spines[['top','right']].set_visible(False)
    fig.savefig(out/'label_shift.png',dpi=170);plt.close(fig)
    pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'));pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
    styles={name:ParagraphStyle(name,fontName='MalgunBold' if name in ['title','h1','h2'] else 'Malgun',fontSize=size,leading=lead,
        textColor=colors.HexColor('#173246' if name in ['title','h1','h2'] else '#273544'),wordWrap='CJK',spaceAfter=space)
        for name,size,lead,space in [('title',25,34,20),('h1',18,26,16),('h2',12,18,8),('body',10,16,10),('small',8.2,12,7)]}
    story=[]
    def p(t,style='body'):return Paragraph(t,styles[style])
    def text(t,style='body'):story.append(p(t,style))
    def table(rows,widths):
        t=Table([[p(html.escape(str(c)),'small') for c in row] for row in rows],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5eff2')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#80a7ae')),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#dae2e8')),
            ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.extend([t,Spacer(1,10)])
    def page():story.append(PageBreak())
    def f(v):return f'{v:.4f}'
    old=two['regression']['all']['first']['pooled'];new=two['regression']['all']['both']['pooled']
    text('전북 고속도로 미관측 지점<br/>온도 추정과 결빙 탐지','title')
    text('입상 목표의 모델·자료·검증 재검토 | 2026.10.24','h2')
    text('문제는 관측 장비가 없는 도로에서도 같은 시각의 노면온도와 결빙 여부를 추정하는 것이다. 기상 자료와 도로 환경을 연결하고, 미관측 지역으로 옮겨도 성능이 유지되는지 확인했다.')
    table([['이번 실제 작업','범위'],['분류 선택 재설계','기존 7종 + 새 2종, 지역 이중 제외, 일별 F1 목적, 새 분류 학습 20건'],
        ['학습 자료 확장','비보호 23곳·두 겨울 794,545행. 4개 외부 지역을 두 겨울 모두 제외'],
        ['추가 모델 비교','온도 대조 16건 + 두 겨울 분류 20건. 비교 56건과 최종 모델 2건 신규 학습'],
        ['핵심 온도 결과',f"동일 두 겨울 MAE {old['mae']:.4f} → {new['mae']:.4f}°C. 아래 지역·계절별 결과로 함께 판단"],
        ['채택 판단','두 겨울 온도 후보: '+('개발상 채택 기준 충족' if audit['temperature_adopt'] else '사전 채택 기준 미충족')]], [112,403])
    text('핵심 발견','h2')
    text('첫 겨울에서 결빙의 대부분을 차지하던 지점의 상태 분포가 다음 겨울에는 크게 달랐다. 첫 겨울의 최고 F1 하나만으로 최종 방식을 결정하면 지역·겨울 편중을 놓친다. 복잡한 분류기 추가가 개선을 보장하지 않는다는 사실도 실제 공간 제외 실험으로 확인했다.')
    text('이 보고서는 반복 개발 검증이다. 보호 3곳의 정답은 이번 학습·선택·검증에 사용하지 않았다. 비보호 둘째 겨울을 개발에 편입했으므로 과거 시간 보류평가는 새 후보의 독립 평가로 사용할 수 없다.','small')
    page();text('01  문제에 맞춘 데이터와 검증','h1')
    text('공식 보존 문제 설명은 두 겨울을 분석 대상으로 하며 부곡교 12410·삼봉 33411·해전 23402를 학습에서 제외하도록 지정한다. 이 범위를 유지하면서 비보호 둘째 겨울을 새로운 개발본에 편입했다. 미래 계절 예보와 같은 시각 미관측 위치 추정을 구별한다.')
    table([['경계','적용'],['금지 대상','보호 12410·33411·23402의 정답, 그 지점의 과거 정답·주변 참조'],['입력','ASOS·AWS 기상 12변수. 분류 확장에는 6/24시간 과거 기상 통계'],
        ['공간 분리','외부 지역 G의 모든 지점을 두 겨울 모두 학습 제외. 선택용 H도 추가 제외'],['시간 경계','목표 시각보다 이른 기상. 이력 통계는 [t-window,t), 유효 슬롯 80% 이상'],
        ['온도 대조','동일 구조·설정으로 첫 겨울 학습과 두 겨울 학습 비교. 같은 지점·시각에서 오차 계산'],['분류 선택','일별 F1 → 지점 평균. 미정의 지점이 사라지는 이점을 막기 위해 선택 시 전체 지점 수 고정']], [100,415])
    text('검증 설계의 의미','h2')
    text('행을 임의로 섞지 않고 지역을 제외해야 관측 장비가 없는 곳에서의 오차를 볼 수 있다. 임계값은 모델 적합에 사용한 행이나 외부 평가 지역에서 고르지 않는다. 다만 여러 실험에 같은 개발 지역을 사용했으므로 연구자의 반복 선택 편향까지 없어진 것은 아니다. [1, 2]')
    text('비보호 둘째 겨울 자료의 지위 변경은 별도 설정·원본 해시로 기록했다. 과거 평가·봉인 파일을 고치거나 새 결과로 덮어쓰지 않았다. 새 후보에 사용할 수 있는 독립 지점은 아직 확보하지 못했다.','small')
    page();text('02  온도 추정: 평균과 지역을 함께 검토','h1')
    story.append(Image(str(out/'temperature.png'),width=515,height=241));story.append(Spacer(1,10))
    rows=[['평가 범위','첫 겨울 학습 MAE','두 겨울 학습 MAE','차이']]
    for period,label in [('2024','2024/25'),('2025','2025/26'),('all','두 겨울 통합')]:
        a=two['regression'][period]['first']['pooled']['mae'];b=two['regression'][period]['both']['pooled']['mae']
        rows.append([label,f(a),f(b),f(b-a)])
    table(rows,[140,125,125,125])
    text('기상 12변수, HistGradientBoosting 회귀 300회, MSE·MAE 모델의 고정 평균이다. 두 겨울 통합 MAE는 6.08%, 둘째 겨울은 13.47% 개선했으나 첫 겨울은 3.88% 악화했다. 결빙점 부근(-2~2°C)의 MAE는 1.2676 → 1.2090°C로 개선했다.')
    text('사전 기준 5개 모두 충족: 통합·지점 균등 MAE 개선, 각 겨울·결빙점 부근 악화 5% 이내, 4지역 중 3개 이상 비악화. 실제 4지역 모두 개선. 새 대조군은 행 순서까지 맞춰 재학습했으므로 예전 1.200531과 소폭 다르다. 위 통합값과 예전 첫 겨울값을 직접 비교하지 않는다.','small')
    page();text('03  결빙 탐지: F1 최적화의 실제 결과','h1')
    rows=[['첫 겨울 공간 개발','일별 지점 F1','FP','FN','탐지 사건']]
    for method,label in [('pred_current','기존 온도·수분'),('pred_asos','ASOS 기온 ≤0°C'),('pred_selected','새 중첩 선택 절차')]:
        r=first['reports'][method];e=firstaudit['events'][method]
        rows.append([label,f(r['coverage']['144']['f1_fixed_population']),f"{r['fp']:,}",f"{r['fn']:,}",f"{e['detected_events']}/347"])
    table(rows,[170,90,85,85,85])
    text('학습 길이·가중치·알고리즘을 바꾼 기존 7종과 과거 기상 이력의 새 2종을 비교했다. 0/30/120분 점수 평활화와 64개 고정 임계값을 내부 지역에서 선택했으나, 선택 절차의 외부 F1은 0.0121로 떨어졌다. 단순 기준선보다 낮아 이 절차를 최종 분류기로 채택하지 않는다.')
    rows=[['두 겨울 확장 후','통합 F1','2024/25','2025/26']]
    for method,label in [('pred_asos','기온 기준선'),('pred_unweighted','무가중 이력 분류'),('pred_weighted20','양성 가중 이력 분류'),('pred_selected','지역 내부 선택')]:
        rows.append([label,*[f(two['classification'][p][method]['f1_fixed_population']) for p in ['all','2024','2025']]])
    table(rows,[200,105,105,105])
    a=audit['physical']['first']['all'];b=audit['physical']['both']['all']
    text(f"최종 온도·수분 판정의 두 겨울 F1은 {a['f1_fixed_population']:.6f} → {b['f1_fixed_population']:.6f}, 일별 지점 평균 Recall은 {a['recall_available_station_mean']:.4f} → {b['recall_available_station_mean']:.4f}이다. 온도 개선을 결빙 탐지 개선으로 확대 해석하지 않는다. 실제 제출 runtime으로 재실행하고 입력 부족은 null로 유지해 유효 쌍에서 제외했다. 전체 지점 고정 평균의 미정의 지점 0은 선택 규약이며 공식 규약으로 주장하지 않는다. 가용 지점 평균·분모·Precision·Recall은 JSON·CSV에 제공한다. [3, 4]",'small')
    page();text('04  결빙 분포 변화와 해석의 한계','h1')
    story.append(Image(str(out/'label_shift.png'),width=515,height=236));story.append(Spacer(1,10))
    text('33408의 Ice는 6,340 → 14슬롯으로 감소했다. 다른 지점에도 결빙 기록이 극히 적거나 없는 기간이 많다. 기상·도로 관리·센서 응답 중 어느 원인이 작용했는지는 이번 자료만으로 확정하지 않는다.')
    text('이 때문에 첫 겨울 33408에 잘 맞는 기온 기준선의 평균 우위가 다른 지역·겨울의 우위를 뜻하지 않는다. 목표를 F1로 바꾸고 탐색 폭만 넓혀도 지역 외삽은 해결되지 않았다. 지점별 실제 결빙 수·유효 관측량과 함께 결과를 제시해야 한다.')
    table([['추정·관측','보고서에서의 의미'],['추정 노면온도','연속 온도값. 결빙 관측 04와 동일한 목표가 아님'],['저온·수분 조건','기상·추정 온도가 조건을 충족한 시간. 실제 빙판 지속시간·사고확률이 아님'],['교량·터널 속성','도로 코드와 길이 비율. 현장 시설 범위·사고 위험 가중치 검증은 별도'],['공유 기상 그룹','1,266개 구간을 138개 두 겨울 입력 그룹에 연결. 독립 표본 1,266개를 의미하지 않음']], [120,395])
    text('RoadSurf의 열·수분 저장량 분리와 입력·현지 물성 의존성을 참고했다. 확보되지 않은 염분·제설·교통·도로 물성값을 임의로 채워 물리 모형이 완성됐다고 표현하지 않는다. [5]','small')
    page();text('05  제출물 구성과 재현 근거','h1')
    table([['심사자가 확인할 항목','제공 근거'],['문제·접근·기여','기상 기반 노면 추정, 공간 제외 검증, 지역·계절 변화 진단'],['실행','고정 모델·CLI·자립 실행 노트북·환경·데모'],['데이터 산출','보호 3곳 103,680행, 500m·1km 구간, 그룹 10분 CSV·위치 인덱스'],['결과 설명','온도·결빙·조건 노출 구별, 결측 18행 상태, 환경 상관의 기술통계 한계'],['검증','합성 회귀 검사, 별도 계산한 지표·이력·저장 모델 재실행, 파일 해시'],['재현 자료','새 학습 소스·설정·문맥별 모델 영수증·선택표·지역별 예측과 CSV']], [120,395])
    text('참고 자료와 실제 적용','h2')
    refs=[
        '[1] Roberts et al. (2017), Cross-validation strategies for structured data. DOI: 10.1111/ecog.02881. 공간 분리의 필요성.',
        '[2] Cawley & Talbot (2010), On Over-fitting in Model Selection. jmlr.org/papers/v11/cawley10a.html. 선택 편향과 반복 개발의 한계.',
        '[3] scikit-learn, Tuning the decision threshold for class prediction. scikit-learn.org/stable/modules/classification_threshold.html. 학습·임계값 선택 분리. 실행 환경은 1.6.1 유지.',
        '[4] Lipton et al. (2014), Thresholding Classifiers to Maximize F1 Score. arxiv.org/abs/1402.1892. 집계·임계값의 차이. 일반 이론의 임계값을 현재 일별 평균에 직접 대입하지 않음.',
        '[5] Karsisto et al. (2024), RoadSurf 1.1. gmd.copernicus.org/articles/17/4837/2024/. 온도와 수분 상태 및 입력 품질.',
        '[6] AIDA 공식 문제 PROB_000000000004604 및 Q&A 556·633. 보존 본문은 10월 16일 확인분. 최신 상세 재접근 실패, 결과물 마감은 미확인. 11월 6일은 참가신청 종료일.']
    for ref in refs:text(html.escape(ref),'small')
    text('최종 고정 모델은 23곳·두 겨울 유효 온도 793,149행으로 적합했다. 추론·검산·재학습은 포함 자료로 실행한다. 전체 탐색 재실행은 원 비공개 작업 공간의 입력 경로가 필요하다. 접수 날짜·방식·데모 요구는 최신 공지 확인이 남았다. 대회 제출·외부 공개는 하지 않았다.','small')
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#d3dfe4'));canvas.line(40,37,555,37)
        canvas.setFont('Malgun',8);canvas.setFillColor(colors.HexColor('#647783'))
        canvas.drawString(40,24,'icy-road-ai | 공간·계절 검증과 모델 검토 | 2026.10.24')
        canvas.drawRightString(555,24,str(doc.page))
    target=out/'award_review.pdf'
    SimpleDocTemplate(str(target),pagesize=A4,leftMargin=40,rightMargin=40,topMargin=42,bottomMargin=49).build(story,onFirstPage=footer,onLaterPages=footer)
    document=fitz.open(target)
    if len(document)!=6:raise ValueError(f'Unexpected layout page count: {len(document)}')
    pages=[]
    for i,pageobj in enumerate(document):
        path=out/f'page_{i+1}.png';pageobj.get_pixmap(matrix=fitz.Matrix(1.25,1.25)).save(path);pages.append(path.name)
    (out/'render_receipt.json').write_text(json.dumps(dict(pdf_sha256=sha(target),pages=6,rendered_pages=pages,visual_review_pending=True),indent=2)+'\n','utf-8')
    print(str(target),flush=True)

if __name__=='__main__':main()
