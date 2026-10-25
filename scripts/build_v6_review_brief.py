"""검산된 기존 성과와 최신 실패·입력 진단을 읽기 쉬운 2쪽 검토 PDF로 만든다."""
from pathlib import Path
import html
import sys
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.blind_icing_validation import read,write,now
from src.data_source import sha256_file as sha


def main():
    out=ROOT/'outputs/private/submission_review_v6_20261025'
    if out.exists():raise FileExistsError('Preserve completed brief')
    private=ROOT/'outputs/private';old=private/'submission_candidate_20261025_v5'
    sources={name:private/name/'summary.json' for name in ['residual_icing_20261025_v1','causal_trend_20261025_v1','weather_information_20261025_v1']}
    for name,path in sources.items():
        a=read(path.parent/'audit.json');assert a['status']=='passed' and a['summary_sha256']==sha(path)
    selected=read(old/'research/extended/selection.json');assert selected['status']=='audited_final_selection'
    regression=selected['temperature_report']['regression']['pooled'];residual=read(sources['residual_icing_20261025_v1']);trend=read(sources['causal_trend_20261025_v1'])
    collision=next(r for r in read(sources['weather_information_20261025_v1'])['results'] if r['scope']=='development_9' and r['view']=='weather15')
    out.mkdir(parents=True);target=out/'review_brief.pdf'
    pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'));pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
    navy=colors.HexColor('#193750');muted=colors.HexColor('#536575');teal=colors.HexColor('#167d8d')
    body=dict(fontName='Malgun',fontSize=9.4,leading=14.8,textColor=navy,wordWrap='CJK')
    styles={'body':ParagraphStyle('body',**body,spaceAfter=8),
        'small':ParagraphStyle('small',**(body|dict(fontSize=8.0,leading=12.2)),spaceAfter=6),
        'title':ParagraphStyle('title',fontName='MalgunBold',fontSize=26,leading=35,textColor=navy,wordWrap='CJK',spaceAfter=12),
        'h2':ParagraphStyle('h2',fontName='MalgunBold',fontSize=12,leading=18,textColor=teal,wordWrap='CJK',spaceBefore=10,spaceAfter=7),
        'kicker':ParagraphStyle('kicker',fontName='MalgunBold',fontSize=9,leading=13,textColor=muted,spaceAfter=12)}
    story=[]
    def p(t,style='body'):return Paragraph(t,styles[style])
    def text(t,style='body'):story.append(p(t,style))
    def table(rows,widths):
        t=Table([[p(html.escape(str(c)),'small') for c in row] for row in rows],colWidths=widths,hAlign='LEFT',repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9f1f4')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,teal),('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#dce4e9')),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.append(t);story.append(Spacer(1,5))
    text('2026 DATA·AI 분석 경진대회  /  비공개 검토 v6','kicker')
    text('관측 없는 도로의 온도 추정과<br/>결빙 판단의 검증 범위','title')
    text('공공 기상·열 이력으로 노면온도를 추정하고 1,266개 도로 구간을 지도와 CSV로 탐색합니다. 온도 오차 개선, 결빙 탐지의 한계, 실제 재현 절차를 함께 제시합니다.')
    text('01  현재 채택한 성과','h2')
    table([['대상','확인한 결과','범위'],['노면온도',f'MAE {regression["mae"]:.6f}°C\nRMSE {regression["rmse"]:.6f}°C',f'기존 개발 9곳·두 겨울\n유효 {regression["n"]:,}쌍, 지역 제외 예측'],['결빙 판정','현재 F1 0.026554\n기온 기준선 0.036601','일별 지표를 지점별 평균\n현재 판정은 기준선 미달'],['제출 검토 자산','온도 v3·결빙 v2 유지','모델·CSV 11종·8쪽 보고서\n실행 노트북·구간 탐색·영상']],[89,174,244])
    text('온도 MAE는 앞선 v2의 1.326890°C보다 13.66% 낮습니다. 두 겨울·네 지역·결빙점 부근의 개선을 확인했습니다. 이 결과는 반복 개발 점수이며 공식 점수나 새 독립 검증 점수가 아닙니다. <b>온도 개선을 결빙 탐지 개선으로 해석하지 않습니다.</b>','small')
    text('02  어떤 방법으로 만들었는가','h2')
    text('허용된 23개 지점의 두 겨울 자료로 기상·과거 열 이력·ASOS 태양 위치 63변수의 HGB를 학습했습니다. 비교할 지역 전체를 학습에서 제외하고, 후보 선택 때는 내부 지역도 추가로 제외합니다. 공식 보호 3지점의 정답은 추가 학습·선택에 사용하지 않습니다.')
    text('입력이 부족한 18행은 결측(NA)으로 남깁니다. 지도는 기상 조건과 모델 추정값을 탐색하는 화면이며, 검증된 사고 확률이나 현장 운영용 위험등급을 뜻하지 않습니다. 현재 연구의 분류 점수는 보정된 실제 결빙 확률이 아닙니다.')
    text('03  이 묶음에서 바로 확인할 수 있는 것','h2')
    text('README → 이 요약 → 현재 상태 → 노트북·명령줄 예측 → 구간 탐색 순으로 검토합니다. v6는 이전 실행 자산을 보존하고 최신 연구·검토 문서·해시 검사 도구를 추가합니다. 대회 접수 완료나 외부 공개 결과가 아닙니다.')
    text('근거: research/extended/selection.json, model/model_card.json, docs/delivery/CSV_CONTRACT.md. 2026-10-25 기준.','small')
    story.append(PageBreak())
    text('검증 결과와 다음 개선 조건','title')
    text('04  최신 실험에서 확인한 한계','h2')
    best=max(residual['reports'],key=lambda k:residual['reports'][k]['all']['f1_fixed_population']);r=residual['reports'][best]
    table([['검토','확인 결과','판단'],['기온 시작값 잔차 모델','30모델·49정책\n사후 최고 F1 '+f'{r["all"]["f1_fixed_population"]:.6f}','기존 탐지 47사건 손실\n주 선택 절차도 악화: 미채택'],['과거 기온 변화의 외삽','미래 관측 없이 10정책 비교','주 선택은 기준선으로 복귀\n안정적 개선 미확인'],['동일 기상 입력의 혼합 정답',f'개발 9곳 결빙 {collision["positive_rows"]:,}행 모두\n비결빙과 같은 15변수 입력 존재',f'전량 탐지 시 최소 FP {collision["minimum_fp_if_all_observed_positives_retained"]:,}\n현재 표본·동일 입력 조건의 진단']],[111,193,203])
    text('입력 중복 진단은 정답을 본 뒤 계산한 정보량 분석입니다. 공식 일별 F1의 상한이나 미래 성능이 아닙니다. 지점 식별자를 더해 자료를 구분하는 진단도 수행했지만, 이를 새 지점의 학습 입력이나 성능 개선으로 사용하지 않았습니다.','small')
    text('05  독립 평가와 자료 품질','h2')
    text('새 4지역의 138,240행 예측을 정답 조회 전에 고정했습니다. 주 후보는 평균 F1 상승에도 재현율 하락과 8사건 손실로 미채택했습니다. 성암교의 공식 목록/API 좌표는 22.29km 다르고, 진천터널외부의 결측·중복 상태는 API 원문에서 재현됐습니다. 이미 완료된 정답·점수는 보존했습니다.')
    text('센서 설치·교정 이력과 시각별 제설 원자료는 미확보입니다. CCTV 시설 목록 2,999건은 노선·이정 확인용이며 과거 RWIS 정상 작동이나 실제 결빙을 증명하지 않습니다. 기상자료 허용을 다른 자료의 포괄 허용으로 해석하지 않습니다.','small')
    text('06  포함 파일로 실행·대조','h2')
    text('Python 3.11에서 requirements-notebook.txt를 설치한 뒤 묶음 루트에서 실행합니다. 설치 이후 예측은 포함 자료를 사용합니다. 새 출력 경로를 사용하며 검증은 성공·실패 로그를 보존합니다.')
    table([['명령','확인하는 내용'],['python scripts/review_submission_bundle.py','선언된 전체 파일의 크기·SHA-256·경로·예상 밖 파일 검사'],['python scripts/review_submission_bundle.py --smoke --output local_review/smoke.json','같은 검사 + 예측 144행의 기준 파일 일치 + 노트북 5개 셀 실행']],[290,217])
    text('결과물 제출 날짜·경로는 10월 25일 22:58 KST 공식 재확인에서도 별도 공지 예정입니다. 11월 6일은 참가신청 종료일입니다. 실제 기한은 공식 후속 공지를 기준으로 합니다.','small')
    text('근거: docs/research/RESIDUAL_AND_INFORMATION_20261025.md, docs/competition/OFFICIAL_UPDATE_20261025.md, validation/v6_delivery.json. 원자료·모델·예측은 비공개 보관.','small')
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#d9e3e8'));canvas.line(44,38,A4[0]-44,38);canvas.setFont('Malgun',8);canvas.setFillColor(muted)
        canvas.drawString(44,24,'icy-road-ai · 온도 v3 / 결빙 v2 · 검토 묶음 v6');canvas.drawRightString(A4[0]-44,24,str(doc.page))
    SimpleDocTemplate(str(target),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=38,bottomMargin=49,title='도로 결빙 위험 추정 - 검토 요약 v6',author='icy-road-ai').build(story,onFirstPage=footer,onLaterPages=footer)
    reader=PdfReader(target);assert len(reader.pages)==2
    for page in reader.pages:assert len(page.extract_text())>500
    write(out/'receipt.json',dict(status='review_brief_created',at_utc=now(),pages=2,pdf_sha256=sha(target),source_hashes={p.relative_to(ROOT).as_posix():sha(p) for p in [*sources.values(),old/'research/extended/selection.json']},code_sha256=sha(Path(__file__))))
    print(target,flush=True)


if __name__=='__main__':main()
