"""v12 보고서 24쪽을 보존하고 검산된 풍속 구간 적용·제출 검토 2쪽을 덧붙인다."""
from pathlib import Path
import sys

import fitz
from PIL import Image as PILImage
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.package_submission_channels import read,write,sha

OUT=ROOT/'outputs/private/report_update_20261106_v13'
OLD=ROOT/'outputs/private/submission_candidate_20261101_v12/reports/analysis_report_v12.pdf'
PROJECTION=ROOT/'outputs/private/wind_network_segment_projection_20261102_v1'
FIGURE=ROOT/'docs/images/wind_network_projection_20261102.png'


def main():
    if OUT.exists():raise FileExistsError('Preserve completed report')
    summary=read(PROJECTION/'summary.json');proof=read(PROJECTION/'independent_verification.json')
    assert proof['status']=='passed' and proof['summary_sha256']==sha(PROJECTION/'summary.json')
    assert summary['segment_count']==843 and summary['daily_rows']==202320
    OUT.mkdir()
    pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'))
    pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
    body=ParagraphStyle('body',fontName='Malgun',fontSize=9,leading=15,spaceAfter=8,textColor=colors.HexColor('#243f49'),wordWrap='CJK')
    title=ParagraphStyle('title',parent=body,fontName='MalgunBold',fontSize=19,leading=27,spaceAfter=16)
    heading=ParagraphStyle('heading',parent=body,fontName='MalgunBold',fontSize=11,leading=18,spaceBefore=10)
    small=ParagraphStyle('small',parent=body,fontSize=7.5,leading=12)
    p=lambda text:Paragraph(text,body)
    def table(rows,widths):
        cells=[[Paragraph(str(v),small) for v in row] for row in rows]
        item=Table(cells,colWidths=widths,hAlign='LEFT')
        item.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f1f3')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#cad8dd')),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        return item
    story=[Paragraph('추가 분석 | 채택 풍속의 구간 적용',title),
        p('분석일 2026년 11월 2일 · 제출 묶음 정리 11월 6일. 앞선 24쪽의 기상·노면온도·결빙 결과에 풍속 구간 적용을 보충합니다. 기존 보고서의 풍속 지도·탐색 설명은 당시 버전이며, 현재 구간 풍속은 이 부록과 새 탐색 화면을 따릅니다.'),
        Image(str(FIGURE),width=490,height=490*PILImage.open(FIGURE).height/PILImage.open(FIGURE).width),
        p('주변 AWS 관측망을 사용한 69특성 모형을 500m 843구간의 두 겨울 29,134,080개 10분 시점에 적용했습니다. 일별 202,320행·겨울별 1,686행의 CSV와 GIS를 만들었습니다. 지도는 추정 풍속과 변화량이며 새 실측 정확도를 뜻하지 않습니다.'),
        table([['길이 가중 기술통계','2024/25 겨울','2025/26 겨울'],['이전 / 현재 풍속 평균 (m/s)','1.289395 / 1.237852','1.331831 / 1.288793'],['풍속 입력 범위 이탈 비율','26.40%','30.39%']],[250,120,120]),
        Spacer(1,8),p('범위 이탈은 학습 입력 최솟값·최댓값 밖의 시점 비율입니다. 오차나 확률이 아닙니다. 학습에 없던 ASOS 172 출처 50구간도 계속 표시합니다. 1,718,034개 집계·GIS 값 및 대표 19구간 3,939,840개 재추론 값의 검산을 통과했습니다.'),
        Paragraph('근거: 모델자료 research/latest/wind_network_segment_projection_20261102_v1/ 및 docs/delivery/FOLLOWUP_REVIEW_20261102.md. 지도 원본과 노선별 비교 CSV를 문서자료에도 제공합니다.',small),
        PageBreak(),Paragraph('제출 검토 | 결과와 한계',title),
        p('v13은 기존에 채택한 모형의 구간 결과·CSV·GIS·오프라인 탐색 화면을 맞춘 제출 후보입니다. 새 학습이나 보호 지점 재평가를 수행하지 않았습니다. 최종 실행 모델은 노면온도 v3·결빙 v2이며, F1 우선 대안 프로필은 별도 실행 선택으로 유지합니다.'),
        table([['항목','확인한 결과','해석과 제한'],['노면온도','개발 9곳 MAE 1.145698°C','두 겨울 310,091쌍. 반복 개발 결과'],['기온 / 습도','AWS 우선 대비 MAE 22.10% / 12.91% 감소','개발 4지역 반복 비교. 새 지역 성적 아님'],['풍속','지역 제외 MAE 0.499955m/s','지역·겨울 제외 0.508379m/s. 69특성 유지'],['결빙','v2 일별 지점 F1 0.026554','ASOS 0°C 기준선 0.036601보다 낮음'],['공간 결과','500m 843개 / 1km 423개','같은 도로의 분할. 독립 관측 수 아님']],[75,195,220]),
        Paragraph('추가 이력 후보를 채택하지 않은 이유',heading),
        p('147특성 풍속 후보는 지역 제외 MAE 0.504858m/s, 지역·겨울 제외 0.510674m/s로 현재 모형보다 악화했습니다. 이 후보를 새 성과로 넣지 않고 실패 근거를 보존합니다. 기상 오차 감소를 결빙 탐지 향상으로 해석하지 않습니다.'),
        Paragraph('결빙과 위험도 해석',heading),
        p('결빙은 가장 큰 미해결 과제입니다. 알려진 F1 우선 프로필은 평균 F1·재현율이 높지만 정밀도와 둘째 겨울 F1이 낮습니다. 제설·수분·센서 이력 부재와 관측 품질의 한계가 남아 있습니다. 조건 기준표와 기상 노출 지도는 공식 위험등급·사고확률·자동 제설 지시의 근거로 검증되지 않았습니다.'),
        Paragraph('제출 파일과 남은 확인',heading),
        p('문서자료 ZIP에는 이 26쪽 보고서·풍속 비교 지도·노선별 CSV·조건 기준표·AI 지원 기록을, 모델자료 ZIP에는 기존 실행 자산과 새 집계 CSV·GIS·오프라인 탐색 화면을 넣습니다. 원본 v12와 기존 검증은 보존합니다. 전체 10분 공간 캐시는 기존과 같이 별도 로컬 보관합니다.'),
        p('11월 6일 공식 공지 목록에 참가 승인 처리 안내가 추가됐으나, 상세 공지·참가양식 재다운로드 접근은 실패했습니다. 결과물 마감 날짜·시각과 업로드 용량 제한은 미확인입니다. 참가신청 종료일을 결과물 마감으로 바꾸어 기록하지 않습니다. 계정 승인·제출 이력·참가자 최종 검토도 별도 확인이 필요합니다.'),
        Paragraph('AI 지원: Codex가 기존 근거 검토·파일 정합성 검사·풍속 화면 통합·보고서 보완·로컬 패키징을 지원했습니다. AI가 실행한 검산을 참가자가 직접 수행한 것으로 기재하지 않습니다. 외부 발송·대회 업로드·공개 전환은 수행하지 않았습니다.',small)]
    def footer(canvas,doc):
        canvas.setFont('Malgun',8);canvas.setFillColor(colors.HexColor('#627b85'))
        canvas.drawString(45,25,'전북 고속도로 기상·노면온도·결빙 분석 | v13 부록')
        canvas.drawRightString(550,25,str(24+doc.page))
    appendix=OUT/'appendix.pdf'
    SimpleDocTemplate(str(appendix),pagesize=(595.28,841.89),leftMargin=45,rightMargin=45,topMargin=40,bottomMargin=45).build(story,onFirstPage=footer,onLaterPages=footer)
    assert len(PdfReader(appendix).pages)==2,'Appendix must fit two pages'
    writer=PdfWriter();writer.append(str(OLD));writer.append(str(appendix))
    result=OUT/'analysis_report_v13.pdf'
    with result.open('xb') as stream:writer.write(stream)
    before=fitz.open(OLD);after=fitz.open(result)
    assert len(before)==24 and len(after)==26
    for i in range(24):
        assert before[i].get_pixmap(matrix=fitz.Matrix(1,1)).samples==after[i].get_pixmap(matrix=fitz.Matrix(1,1)).samples
    for i in [24,25]:after[i].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(OUT/f'page_{i+1}.png')
    assert all('풍속' in after[i].get_text() for i in [24,25])
    write(OUT/'build_receipt.json',dict(status='built_pending_visual_review',pages=26,previous_pages_pixel_identical=24,
        pdf_sha256=sha(result),source_pdf_sha256=sha(OLD),source_summary_sha256=sha(PROJECTION/'summary.json'),
        sources={p.relative_to(ROOT).as_posix():sha(p) for p in [Path(__file__),FIGURE,PROJECTION/'independent_verification.json']},renderer='PyMuPDF (Poppler unavailable)'))
    print('REPORT BUILT',len(after),'pages; 24 pages pixel identical',flush=True)


if __name__=='__main__':main()
