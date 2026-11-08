"""안정화 습도·두 검증·새 지도까지 포함한19쪽 보고서의 수치와 조판을 검증한다."""
import argparse
import html
from pathlib import Path
import shutil
import sys
import fitz
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.ops import nearest_points
from matplotlib.lines import Line2D
from markdown_it import MarkdownIt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image,PageBreak,Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_editorial_report import inline,check_claims
from scripts.evaluate_objective_icing import read,write,verify_preserved,now
from src.data_source import sha256_file as sha

from scripts.build_analysis_report_v8 import evidence as previous_evidence

MANUSCRIPT=ROOT/'docs/delivery/ANALYSIS_REPORT_V10_20261101.md'
PRIVATE=ROOT/'outputs/private'
WIDTH=A4[0]-88

def render(manuscript,target):
    pdfmetrics.registerFont(TTFont('UpdateKR','C:/Windows/Fonts/malgun.ttf'))
    pdfmetrics.registerFont(TTFont('UpdateKRBold','C:/Windows/Fonts/malgunbd.ttf'))
    pdfmetrics.registerFontFamily('UpdateKR',normal='UpdateKR',bold='UpdateKRBold',italic='UpdateKR',boldItalic='UpdateKRBold')
    navy=colors.HexColor('#20394c');teal=colors.HexColor('#147f86')
    styles={name:ParagraphStyle(name,fontName='UpdateKRBold' if name.startswith('h') else 'UpdateKR',
        fontSize=size,leading=leading,wordWrap='CJK',textColor=navy,spaceAfter=space,keepWithNext=name.startswith('h'))
        for name,size,leading,space in [('h1',23,32,12),('h2',17,24,12),('h3',11.5,17,7),
            ('body',9.6,15.7,9),('small',8.2,12.3,6),('code',8,12,8)]}
    story=[];headings=[];page=1;in_table=False;rows=[];row=[];number=0
    tokens=MarkdownIt('commonmark').enable('table').parse(manuscript)
    for i,token in enumerate(tokens):
        kind=token.type
        if kind=='html_block':
            assert token.content.strip()=='<!-- page -->';story.append(PageBreak());page+=1
        elif kind=='heading_open':
            item=tokens[i+1];text=inline(item.children)
            if token.tag=='h1':text=text.replace('구간의 ','구간의<br/>',1)
            story.append(Paragraph(text,styles[token.tag]))
            if token.tag in ['h1','h2']:headings.append((page,item.content))
        elif kind=='table_open':in_table=True;rows=[]
        elif kind=='tr_open':row=[]
        elif kind=='inline' and in_table:row.append(Paragraph(inline(token.children),styles['small']))
        elif kind=='tr_close':rows.append(row)
        elif kind=='table_close':
            in_table=False;n=len(rows[0]);ratios={2:[.32,.68],3:[.29,.34,.37],4:[.32,.24,.22,.22]}[n]
            if page==4:ratios=[.48,.26,.26]
            if page==11:ratios=[.30,.22,.22,.26]
            table=Table(rows,colWidths=[WIDTH*r for r in ratios],repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7f0f1')),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.65,teal),
                ('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#dce4e8')),
                ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
                ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
            story.extend([table,Spacer(1,9)])
        elif kind=='ordered_list_open':number=0
        elif kind=='list_item_open':number+=1
        elif kind=='paragraph_open' and not in_table:
            item=tokens[i+1];children=item.children or []
            if len(children)==1 and children[0].type=='image':
                image=children[0];source=(MANUSCRIPT.parent/image.attrGet('src')).resolve()
                with fitz.open(source) as document:rect=document[0].rect
                height=400 if 'weather_projection' in source.name else (230 if 'weather_humidity_stable' in source.name else (210 if 'weather_adopted' in source.name else (240 if 'weather_transfer' in source.name else (280 if 'inventory_comparison' in source.name else 156))))
                scale=min(WIDTH/rect.width,height/rect.height)
                story.extend([Image(str(source),width=rect.width*scale,height=rect.height*scale),Spacer(1,5),
                    Paragraph(html.escape(image.content),styles['small'])])
            else:
                prefix=f'{number}. ' if i>0 and tokens[i-1].type=='list_item_open' else ''
                story.append(Paragraph(prefix+inline(children),styles['body']))
        elif kind=='fence':story.append(Paragraph('<br/>'.join(html.escape(line) for line in token.content.splitlines()),styles['code']))
    assert page==19
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#d8e2e7'));canvas.line(44,38,A4[0]-44,38)
        canvas.setFont('UpdateKR',8);canvas.setFillColor(colors.HexColor('#607380'))
        canvas.drawString(44,24,'icy-road-ai · 분석 기준 2026.11.01 · 비공개 검토본');canvas.drawRightString(A4[0]-44,24,str(doc.page))
    SimpleDocTemplate(str(target),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=40,bottomMargin=50,
        title='미관측 고속도로의 기상·노면온도 추정과 결빙 조건',author='icy-road-ai').build(story,onFirstPage=footer,onLaterPages=footer)
    with fitz.open(target) as document:
        assert len(document)==page,('Page overflow',len(document),page)
        for expected_page,heading in headings:
            assert ''.join(heading.split()) in ''.join(document[expected_page-1].get_text().split()),('Shifted heading',expected_page,heading)
        for p in document:
            for block in p.get_text('dict')['blocks']:
                if block['type']!=0:continue
                for line in block['lines']:
                    for span in line['spans']:
                        x0,y0,x1,y1=span['bbox']
                        assert x0>=40 and x1<=A4[0]-39 and y0>=34 and y1<=A4[1]-18,span['text']
        return len(document)


def evidence(manuscript):
    claims={};paths={}
    names=['weather_humidity_stable_20261101_v1','weather_history_segment_projection_20261101_v1']
    for name in names:
        p=PRIVATE/name;audit=read(p/'independent_verification.json')
        assert audit['status']=='passed' and audit['summary_sha256']==sha(p/'summary.json'),name
        paths[name]=p/'summary.json';paths[name+'_audit']=p/'independent_verification.json'
    weather=read(paths[names[0]]);assert weather['primary_success']
    for mode,report in weather['reports'].items():
        for model in ['instant_residual','stable_history']:
            value=report['metrics'][model]['pooled']['mae'];claims[mode+'_'+model]=f'{value:.6f}'
            assert claims[mode+'_'+model] in manuscript
    for value in ['1.145698','0.026554','0.036601','447,794','29,134,080','202,320','1,686']:
        assert value in manuscript;claims[value]=value
    verification=PRIVATE/'weather_history_supplement_validation_20261101_v2/receipt.json'
    assert read(verification)['status']=='weather_history_supplement_verified';paths['runtime_verification']=verification
    visual=PRIVATE/'weather_history_projection_review_20261101_v1/visual_review.json'
    assert read(visual)['status']=='passed';paths['map_visual']=visual
    return claims,paths


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=PRIVATE/'report_update_20261101_v10_draft1')
    args=parser.parse_args();out=args.output.resolve();assert out.is_relative_to(PRIVATE.resolve())
    if out.exists():raise FileExistsError('Preserve report drafts')
    out.mkdir();frozen=verify_preserved();manuscript=MANUSCRIPT.read_text(encoding='utf8')
    claims,sources=evidence(manuscript)
    for name in ['weather_adopted_20261101.png','weather_humidity_stable_20261101.png','weather_projection_20261101.png','inventory_comparison_20261031_v3.png',
                 'editorial_temperature_20261025.png','editorial_blind_20261025.png']:
        sources[name]=ROOT/'docs/images'/name
    sources['manuscript']=MANUSCRIPT;sources['builder']=Path(__file__)
    shutil.copy2(MANUSCRIPT,out/'analysis_report_v10.md')
    pdf=out/'analysis_report_v10.pdf';pages=render(manuscript,pdf)
    preview=out/'preview';preview.mkdir()
    with fitz.open(pdf) as document:
        for i,page in enumerate(document):page.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(preview/f'page_{i+1:02d}.png')
        (out/'extracted_text.txt').write_text('\n'.join(page.get_text() for page in document),encoding='utf8')
    assert verify_preserved()==frozen
    write(out/'build_receipt.json',dict(status='rendered_pending_visual_review',at_utc=now(),pages=pages,claims=claims,
        sources={p.relative_to(ROOT).as_posix():sha(p) for p in sources.values()},pdf_sha256=sha(pdf),
        preservation=frozen,protected_outcomes_read=False))
    print('V10 REPORT RENDERED',pages,pdf,flush=True)


if __name__=='__main__':main()

