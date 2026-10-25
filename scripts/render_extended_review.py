"""검산 완료된 확장 모델의 결과·한계·문헌 활용을 8쪽 PDF로 작성한다."""
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
from scripts.build_extended_candidate import OUT,read,write


def main():
    private=ROOT/'outputs/private';dest=private/'extended_review_20261024_v1'
    if dest.exists():raise FileExistsError('Preserve previous report rendering')
    selection=read(OUT/'research/extended/selection.json');assert selection['status']=='audited_final_selection'
    comparison=read(private/'extended_completion_20261024_v1/summary.json');reg=selection['temperature_report'];new=reg['regression']
    old=read(private/'two_winter_models_20261024_v1/summary.json')['regression']['all']['both'];ice=read(OUT/'research/extended/audit.json')['physical']['both']
    inference=read(OUT/'validation/extended_inference.json');refit=read(OUT/'validation/refit_comparison.json');assert refit['all_models_byte_identical']
    plan=read(OUT/'extended_training_plan.json');exports=read(OUT/'exports/manifest.json');dest.mkdir()
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
    ids=sorted(new['stations']);y=np.arange(len(ids));fig,ax=plt.subplots(figsize=(9.4,4.4),layout='constrained')
    ax.barh(y-.18,[old['stations'][s]['mae'] for s in ids],height=.34,label='기존 v2',color='#a3b3c3');ax.barh(y+.18,[new['stations'][s]['mae'] for s in ids],height=.34,label='확장 v3',color='#087f8c')
    ax.set_yticks(y,ids);ax.invert_yaxis();ax.set_xlabel('같은 지역 제외 예측의 MAE (°C)');ax.legend();ax.spines[['top','right']].set_visible(False)
    fig.savefig(dest/'station_mae.png',dpi=180);plt.close(fig)
    iterations=[600,1200,2400];allreports=comparison['regression_reports'];fig,ax=plt.subplots(figsize=(9.4,3.3),layout='constrained')
    for prefix,label,color in [('combined_history','기상·열 이력 61개','#9daec1'),('combined_asos_solar','기상·열 이력 + 태양 63개','#087f8c')]:
        ax.plot(iterations,[allreports[f'{prefix}_mae{n}']['regression']['pooled']['mae'] for n in iterations],marker='o',label=label,color=color)
    ax.set_xticks(iterations);ax.set_xlabel('학습 반복 수');ax.set_ylabel('MAE (°C)');ax.legend();ax.spines[['top','right']].set_visible(False)
    fig.savefig(dest/'capacity.png',dpi=180);plt.close(fig)
    pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'));pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
    styles={name:ParagraphStyle(name,fontName='MalgunBold' if name in ['title','h1','h2'] else 'Malgun',fontSize=size,leading=leading,
        textColor=colors.HexColor('#173246'),wordWrap='CJK',spaceAfter=space) for name,size,leading,space in
        [('title',25,35,19),('h1',18,26,16),('h2',12,19,9),('body',10,16,10),('small',8.4,13,7)]}
    story=[]
    def para(t,style='body'):return Paragraph(t,styles[style])
    def text(t,style='body'):story.append(para(t,style))
    def table(rows,widths):
        t=Table([[para(html.escape(str(c)),'small') for c in row] for row in rows],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5eff2')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#80a7ae')),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#dae2e8')),
            ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.extend([t,Spacer(1,9)])
    def page():story.append(PageBreak())
    def number(v):return f'{v:.4f}'
    gain=1-new['pooled']['mae']/old['pooled']['mae']
    text('고속도로 미관측 지점의<br/>노면온도 추정과 결빙 조건','title')
    text('기상·열 이력 모델 고도화 및 제출 검토 | 2026.10.24 | v3','h2')
    text('노면 센서가 없는 위치에 같은 시각의 노면온도와 결빙 조건을 제공한다. 공공 기상, 과거 열 상태와 태양 위치를 결합하고, 평가 지역의 두 겨울 전체를 학습에서 제외해 전이 성능을 비교했다.')
    table([['핵심 결과','같은 개발 범위에서 확인한 변화'],['통합 온도 MAE',f"{old['pooled']['mae']:.4f} → {new['pooled']['mae']:.4f}°C / {gain:.2%} 감소"],
        ['결빙점 부근 MAE',f"{old['near_freezing']['mae']:.4f} → {new['near_freezing']['mae']:.4f}°C / 관측 -2~2°C"],
        ['지역·계절 검토','통합·지점 평균·두 겨울·각 지점·결빙점 부근·지역 지지의 6개 기준 모두 충족'],
        ['결빙 탐지',f"v2 판정 유지 / 일별 지점 F1 {ice['all']['f1_fixed_population']:.6f}. 온도 개선과 구분"],
        ['제출 구성','고정 학습·추론 코드, 포함 학습 자료, CSV 11종, 지도, 실행 노트북, 실제 출력 데모']], [120,395])
    text('이번 고도화의 기여','h2')
    text('문헌의 열 상태·시간척도 아이디어를 보호 노면 정답 없이 구현했다. 원천 기상과 재구성한 입력을 대조하고, 연구 특징과 실행 특징을 전량 비교했다. 성능표와 실제 제출 실행이 다른 입력·모델을 사용하지 않도록 검산했다.')
    text('반복 개발 평가이며 공식 성적이나 새 독립 평가가 아니다. 허용 비보호 둘째 겨울도 개발에 사용했다. 보호 12410·33411·23402의 정답은 새 학습·선택·검증에서 읽지 않았다. 입상이나 현장 안전성을 보장하는 결과로 해석하지 않는다.','small')
    page();text('01  자료와 추론 경계','h1')
    table([['항목','적용 내용'],['학습 범위','허용 23곳 · 2024/25 및 2025/26 겨울. 원시 794,545행, 유효 온도 학습 쌍 793,149행'],
        ['기상 12개','ASOS·AWS 기온, 습도, 바람, 강수, 이슬점, 관측 시차 및 주기 시각'],
        ['열·수분 10개','ASOS 지면온도·운량·일사·강수·적설·습도, 과거 저온·강수와 온도차'],
        ['과거 기상 30개','6개 기상 변수의 1·3·12시간 평균과 1·3시간 변화'],
        ['과거 열 상태 9개','ASOS 지면온도·운량·일사의 1·3·12시간 평균'],
        ['태양 2개','연결 ASOS 좌표의 태양 고도와 양의 사인. 실제 복사량 실측이 아님'],
        ['금지 입력','보호 노면 실측·과거 노면 정답·외부 노면 정답·사전학습 외부 가중치 미사용'],
        ['시간·결측','기상은 목표보다 이른 관측, 이력은 [t-window,t). 과거 유효 슬롯 80% 필요. 미래 보간·결측 0 대체 없음']], [120,395])
    text('입력 검산에서 발견한 정정','h2')
    text('원천 AWS·ASOS를 별도로 연결한 검산에서 학습 부분 113행의 기상값 540개 차이를 발견했다. 기존 자료와 실험은 보존하고 정정 입력으로 후보를 다시 학습했다. 외부 개발 9곳의 기존 평가 입력은 같았다. 정정 후 입력 유효 793,209행과 온도 정답까지 유효한 793,149행을 구분한다.')
    text('63개 실행 특징의 전체 값 50,056,335개를 연구 특징과 대조했다. 별도 54·63개 대조를 합쳐 143,018,100개 값이 허용 오차 내에서 일치했다. 정수 누적합·반올림을 고정해 배치 크기에 따른 트리 분기 변화를 방지했다.','small')
    page();text('02  공간 제외 온도 검증','h1')
    story.append(Image(str(dest/'station_mae.png'),width=515,height=241));story.append(Spacer(1,8))
    rows=[['범위','기존 v2 MAE','확장 v3 MAE','변화']]
    for year,label in [('2024','2024/25'),('2025','2025/26')]:
        a=reg['winters'][year]['baseline']['pooled']['mae'];b=reg['winters'][year]['new']['pooled']['mae'];rows.append([label,number(a),number(b),f'{(b/a-1):+.2%}'])
    rows.append(['통합',number(old['pooled']['mae']),number(new['pooled']['mae']),f'{-gain:.2%}']);table(rows,[140,125,125,125])
    text(f"통합 RMSE {new['pooled']['rmse']:.4f}°C, BIAS {new['pooled']['bias']:+.4f}°C. 유효 온도 비교 쌍 {new['pooled']['n']:,}행. BIAS는 추정−관측이다.")
    text('4개 지역의 모든 지점을 두 겨울 모두 제외한다. 지점·날짜를 무작위로 섞지 않으며, 제외 지역의 점수로 학습을 조기 종료하지 않는다. 다만 같은 개발 지역을 반복 비교했으므로 후보 선택 편향은 남는다.')
    diag=comparison['diagnostics'][selection['simpler_reference']]['date_sensitivity']['relative_improvement_quantiles']
    text(f"단순 기준 후보의 7일 날짜 블록 재표집 2,000회에서 개선율 2.5·50·97.5 백분위는 {diag[0]:.2%}, {diag[1]:.2%}, {diag[2]:.2%}였다. 고정된 9곳·후보에 조건부인 날짜 민감도이며, 새로운 지역이나 모델 선택의 신뢰구간이 아니다.",'small')
    page();text('03  넓은 탐색과 개선 둔화 확인','h1')
    text(f"확장 회귀 설정 {comparison['regression_candidates']}개를 같은 개발 분할로 비교했다. HGB·LightGBM·XGBoost·CatBoost·자체 MLP, 잔차 학습, 지역 가중치, 입력 제거, 과거 상태, 태양·지형을 포함한다. 연구 원본을 바꾸지 않고 후속 대조를 별도 폴더에 저장했다.")
    story.append(Image(str(dest/'capacity.png'),width=515,height=181));story.append(Spacer(1,8))
    table([['대조','관찰·채택 기준'],['학습 길이',f"ASOS 태양 모델 1,200 → 2,400회의 MAE 개선 {selection['last_capacity_relative_improvement']:.3%}. 0.5% 미만"],
        ['태양 좌표',f"ASOS 위치와 대상 위치의 600회 MAE 차이 {selection['asos_geometry_relative_gap']:.3%}. 사전 0.5% 이내 조건 충족"],
        ['난수 시드', '1,200회 세 시드 MAE: '+', '.join(f'{v:.5f}' for v in selection['seed_mae'].values())],
        ['고정 평균','3시드 평균·태양/비태양 평균·1,200/2,400 평균·MAE/MSE 평균 비교. 추가 0.5% 이상 개선일 때만 복잡성 증가 허용'],
        ['최종 구성',selection['selected']]], [115,400])
    text('탐색한 알고리즘·입력·학습량 방향에서 성능 이득이 둔화되는지를 확인했다. 모든 방법의 개선 불가능성은 입증할 수 없다. 추가 독립 지역, 노면의 실제 물성·제설·교통 자료는 이번 비교로 해결하지 못한 연구 과제다.','small')
    blend=comparison['fixed_blend_reports']['asos_solar1200_three_seed_mean']['regression']['pooled']['mae']
    text(f"3시드 평균의 MAE {blend:.6f}°C는 단일 기준보다 약 {(1-blend/allreports['combined_asos_solar_mae1200']['regression']['pooled']['mae']):.2%} 낮았다. 이 작은 이득도 숨기지 않고 보존했다. 다만 사전에 정한 복잡성 증가 기준 0.5%에는 못 미쳐 기본 제출 모델은 단일 시드를 유지한다.",'small')
    page();text('04  결빙 탐지는 별도로 판단','h1')
    terrain=comparison['classification']['terrain_classification_20261024_v1']['reports'];thermal=comparison['classification']['thermal_classification_20261024_v1']['reports']
    rows=[['방법','통합 F1','2024/25 F1','2025/26 F1']]
    rows.append(['유지한 v2 조건',*[f"{ice[y]['f1_fixed_population']:.6f}" for y in ['all','2024','2025']]])
    for name,r in [('ASOS 기온 ≤0°C',terrain['asos_zero']),('열·기상 중첩 선택',thermal['selected_worst_winter_f1']),('지형 포함 중첩 선택',terrain['selected_worst_winter_f1'])]:rows.append([name,*[f"{r[y]['f1_fixed_population']:.6f}" for y in ['all','2024','2025']]])
    table(rows,[200,105,105,105])
    text('위 ASOS 기준선은 v2와 같은 입력 가용 범위로 재계산했다. 기본 개발 CSV에 보존한 0.036392는 기상 결측을 0으로 처리한 기존 비교 정책의 값이므로 구별한다. 새 분류 대조의 원 보고도 함께 제공한다.','small')
    text('분류기 6개 설정에 지역 1곳·2곳 제외 문맥을 적용해 60개 모델을 적합했다. 외부 지역 G의 임계값 선택용 H도 모델 학습에서 제외한다. 고정 64개 임계값을 평균 F1 및 최저 겨울 F1 기준으로 비교했다. 별도 648개 기상 규칙과 10개 고정 조합도 검토했다.')
    text('새 방법은 F1 향상·Precision·Recall·두 겨울·각 지점·기존 탐지 사건 보존의 모든 기준을 동시에 통과하지 못했다. 높은 평균 F1을 얻은 후보도 손실을 함께 표시한다. 단순 ASOS 기온 기준선은 평균 F1과 Recall에서 v2보다 높지만, Precision과 일부 지점·둘째 겨울에서 불리했다.')
    text('현재 추정 온도와 결빙 기준 온도','h2')
    text('온도 회귀 개선을 그대로 결빙 개선으로 해석하지 않는다. 결빙은 기존 v2 온도 ≤0°C이면서 이슬점·강수·적설 중 수분 근거가 있는 규칙을 유지한다. CSV와 화면에는 새 추정 온도와 결빙 기준 온도를 따로 제공한다. 조건 노출은 관측 결빙률·사고확률이 아니다.')
    text('일별 지표를 지점별로 평균한다. 미정의 지점의 F1=0은 후보 선택 규약이며 공식 확정 규약으로 주장하지 않는다. 144·130·72·1 슬롯 조건과 가용 지점 평균·날짜 수·FP/FN은 CSV로 제공한다. 결측 예측은 음성으로 계산하지 않는다.','small')
    page();text('05  전체 공간 산출과 실행 예제','h1')
    story.append(Image(str(OUT/'figures/candidate_condition_map_500m.jpg'),width=515,height=371));story.append(Spacer(1,8))
    table([['산출물','범위'],['10분 자료',f"138개 기상 그룹 · {inference['group_rows']:,}행. 위치 인덱스로 전체 구간 연결"],['구간','500m 843개 + 1km 423개. 두 겨울 속성 2,532행'],['보호 예측','3곳 103,680행, 입력 부족 18행은 NA. 보호 정답 없음'],['실행 예제','과거 12시간을 포함한 216행 입력 → 하루 144행 출력. 실제 CLI·HTML·12초 영상']], [115,400])
    text('지도는 같은 결빙 판정을 유지하므로 v2와 조건 노출이 같다. 갱신된 구간 속성에는 현재 평균 추정 온도를 반영했다. 공유 기상 그룹·겹치는 구간을 독립 검증 표본으로 세지 않는다. 교량·터널 속성과 추정값의 상관은 관측 결빙·사고의 인과효과가 아니다.','small')
    page();text('06  재현성과 제출 검토','h1')
    table([['검사','실제 산출 근거'],['재학습',f"포함 자료·고정 계획으로 {len(plan['models'])}개 모델을 독립 재학습. 모든 모델 파일의 SHA-256 일치"],
        ['연구 예측','선택 모델의 저장 파일 재실행, 학습 지점 제외·행키·예측·MAE/RMSE 검산'],
        ['실행 입력','원천 기상 대조, 54·61·63개 연구/실행 특징 전체 일치 검사'],
        ['실제 추론','전체 기상 그룹 추론. 기존 결빙 판정과 기준 온도는 행별 정확히 보존'],
        ['CSV','11종의 키·행 수·결측·모든 숫자 재독해. 그룹과 보호 예측의 연결 일치'],
        ['노트북','실제 Jupyter 커널의 5개 코드 셀: 자료·모델 해시, 추론, 개발 지표, CSV'],
        ['실행 화면','데스크톱·모바일, 시각 슬라이더, 두 온도·판정 값, 외부 요청·오류 검사'],
        ['보존','이전 ZIP과 기존 봉인 47·549개 파일 유지. 대회 제출·외부 공개 미수행']], [115,400])
    text('현재 묶음의 실행 진입점','h2')
    for s in ['code/predict.py: 포함된 기상 입력에서 예측. --output-start/--output-end는 이력 계산 뒤 적용한다.',
              'code/train.py: extended_training_plan.json의 포함 학습 자료로 새 출력 폴더에 재학습한다.',
              'notebooks/extended_submission_review.ipynb: 기본 실행에서 재학습하지 않고 현재 묶음을 검산한다.',
              'exports/manifest.json: 파일별 키·열·결측·해시. 루트 manifest.json: 전체 구성 파일의 무결성.',
              '전체 탐색 재실행은 원 비공개 작업 공간의 자료가 필요하다. 과거 연구 소스를 현재 독립 실행 범위와 구별한다.']:text(html.escape(s),'small')
    page();text('07  문헌·공개 자료와 이용 조건','h1')
    refs=[
      ('Li et al., GMD 2026','https://gmd.copernicus.org/articles/19/9035/2026/','열 상태·다중 시간척도를 참고. 과거 노면온도와 지점별 학습을 사용하는 원 논문의 성능을 공간 전이 점수로 옮기지 않음. Zenodo 코드·가중치 미도입.'),
      ('MSTF-Net, iScience 2026','https://github.com/Oneeer/MSTF-Net','이론 기반 시간척도 아이디어만 참고. 저장소 이용조건·코드 본문 확인이 제한돼 외부 코드·중국 관측자료·가중치 미복사.'),
      ('FMI RoadSurf-Python / RoadSurf 1.1','https://github.com/fmidev/RoadSurf-Python','README MIT. 온도·수분 상태의 구분 참고. Python 변환본의 연구용 한계를 기록하며 원 구현 재현이라고 주장하지 않음.'),
      ('TabM / Chronos-2 / TabPFN-2.5','https://github.com/yandex-research/tabm','TabM Apache-2.0이나 배포본 확보 실패. Chronos-2는 목표 이력 조건, TabPFN은 별도 가중치 이용조건·규모 적합성을 검토해 미도입. 자체 MLP는 이들의 재현이 아님.'),
      ('NOAA 태양 위치 식','https://gml.noaa.gov/grad/solcalc/solareqns.PDF','윤년·동경·UTC+9를 반영한 태양 고도 근사. 대기 굴절 미보정. 외부 예측 API 또는 사전학습 가중치가 아님.'),
      ('Copernicus GLO-30','https://registry.opendata.aws/copernicus-dem/','기존 공개 DSM 4타일을 지형 대조에만 사용. 건물·수목 포함 DSM이며 도로 바닥·교량 정답이 아님. 지형 회귀 후보 미채택. 원 EULA·가공 고지 보존.')]
    for title,url,body in refs:
        text(f'<link href="{html.escape(url,quote=True)}" color="#087f8c">{html.escape(title)}</link>','h2');text(html.escape(body),'small')
    text('대회 규정 확인 범위','h2')
    text('10월 16일 마지막 전체 확인본의 Q&amp;A 588은 출처·근거를 밝힌 공개 공공 기상을 허용하고 보호 노면 정답의 외부 확보·사용을 금지한다. 10월 24일 공개 소개·공지·Q&amp;A 목록은 재확인했지만 상세 답변·최신 참가서약 재조회는 실패했다. 최신 규정 불변이나 특정 도구의 개별 승인을 단정하지 않는다.','small')
    text('11월 6일은 참가신청 종료일, 공개 소개의 11월 25일은 전체 일정·시상식 종료일이다. 실제 결과물 마감은 별도 확인이 필요하다. 외부 사전학습 가중치와 데이터 업로드는 사용하지 않았다. 설치 의존성의 버전·고지는 licenses/, AI 활용과 사람의 검토 범위는 AI_USAGE.md에 기록했다.','small')
    def footer(c,doc):
        c.setStrokeColor(colors.HexColor('#d3dfe4'));c.line(40,37,555,37);c.setFont('Malgun',8);c.setFillColor(colors.HexColor('#647783'))
        c.drawString(40,24,'icy-road-ai | 비공개 제출 검토 후보 v3 | 2026.10.24');c.drawRightString(555,24,str(doc.page))
    target=dest/'extended_review.pdf';SimpleDocTemplate(str(target),pagesize=A4,leftMargin=40,rightMargin=40,topMargin=42,bottomMargin=49).build(story,onFirstPage=footer,onLaterPages=footer)
    document=fitz.open(target);assert len(document)==8,len(document);pages=[]
    for i,p in enumerate(document):
        path=dest/f'page_{i+1}.png';p.get_pixmap(matrix=fitz.Matrix(1.25,1.25)).save(path);pages.append(path.name)
    write(dest/'render_receipt.json',dict(pdf_sha256=sha(target),pages=8,rendered_pages=pages,visual_review_pending=True))
    print(target,flush=True)


if __name__=='__main__':main()
