"""13쪽 통합 원고·공식 목록 지도를 조판하고 수치·페이지 경계를 검증한다."""
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

MANUSCRIPT=ROOT/'docs/delivery/ANALYSIS_REPORT_20261031.md'
PRIVATE=ROOT/'outputs/private'
WIDTH=A4[0]-88


def evidence(manuscript):
    paths={'selection':PRIVATE/'submission_candidate_20261026_v7/research/extended/selection.json',
        'ice':PRIVATE/'submission_candidate_20261026_v7/research/extended/audit.json',
        'baseline':PRIVATE/'two_winter_models_20261024_v1/summary.json',
        'comparison':PRIVATE/'extended_completion_20261024_v1/summary.json',
        'blind':PRIVATE/'blind_icing_20261025_v2/summary.json'}
    data={name:read(path) for name,path in paths.items()};claims=check_claims(manuscript,data)
    studies=['objective_icing_20261031_v2','reanalysis_temperature_20261031_v1',
        'reanalysis_icing_20261031_v1','antecedent_forcing_20261031_v2']
    for name in studies:
        p=PRIVATE/name;record=read(p/'summary.json');audit=read(p/'independent_verification.json')
        assert audit['status']=='passed' and audit['summary_sha256']==sha(p/'summary.json')
        paths[name]=p/'summary.json';paths[name+'_audit']=p/'independent_verification.json'
        if name.startswith('reanalysis_temperature'):
            value=record['reports']['era5_raw']['regression']['pooled']['mae']
        else:
            key='selected_mean_f1' if name.startswith('reanalysis_icing') else 'mean_f1'
            value=record['reports'][key]['all']['f1_fixed_population']
        claims[name]=f'{value:.6f}';assert claims[name] in manuscript
    for name in ['official_chainage_alignment_20261031_v1','vulnerability_map_comparison_20261031_v1','official_inventory_viewer_20261031_v1']:
        paths[name]=PRIVATE/name/'summary.json'
    alignment=read(paths['official_chainage_alignment_20261031_v1'])
    for name,value in [('chainage_mae',alignment['validation']['contiguous_5km_block']['mae_m']),
        ('chainage_p95',alignment['validation']['contiguous_5km_block']['p95_abs_m']),
        ('cctv_mae',alignment['cctv_diagnostic']['mae_m']),('cctv_p95',alignment['cctv_diagnostic']['p95_abs_m'])]:
        claims[name]=f'{value:,.2f}';assert claims[name] in manuscript
    audit=PRIVATE/'vulnerability_map_comparison_20261031_v1/independent_verification.json'
    assert read(audit)['status']=='passed';paths['spatial_audit']=audit
    assert read(paths['official_inventory_viewer_20261031_v1'])['directional_corridors']==8
    return claims,paths


def map_figure(destination):
    source=PRIVATE/'vulnerability_map_comparison_20261031_v1/comparison.gpkg'
    roads=gpd.read_file(source,layer='two_winter_screening')
    inventory=gpd.read_file(source,layer='estimated_inventory_overlay')
    boundary=gpd.read_file(PRIVATE/'segment_exposure_20261009_v1/boundary.gpkg').to_crs(roads.crs)
    assert roads.crs.to_epsg()==5179 and len(roads)==843
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':9})
    fig,axes=plt.subplots(1,2,figsize=(9.4,5.2))
    fig.subplots_adjust(left=.01,right=.99,bottom=.10,top=.93,wspace=.05)
    limits=roads.total_bounds;pad=5500
    for ax,version,title in zip(axes,['problem_undated','2026-09-07'],['문제 제시 목록 · 기준일 미상','최신 목록 · 2026.09.07']):
        boundary.plot(ax=ax,facecolor='#f2f4f5',edgecolor='#bbc5ce',linewidth=.5)
        roads.plot(ax=ax,color='#b5c1cc',linewidth=1.2)
        roads.loc[roads.field_review_candidate].plot(ax=ax,color='#de9424',linewidth=3)
        inventory.loc[inventory.version.eq(version)].plot(ax=ax,color='#147f86',linewidth=2.4)
        roads.loc[~roads.chainage_available].plot(ax=ax,color='#8c4b8d',linewidth=2)
        ax.set(xlim=(limits[0]-pad,limits[2]+pad),ylim=(limits[1]-pad,limits[3]+pad),title=title)
        ax.set_axis_off()
        ax.annotate('N',xy=(.94,.94),xytext=(.94,.82),xycoords='axes fraction',ha='center',
            arrowprops={'arrowstyle':'-|>','color':'#30475c'},fontsize=9,color='#30475c')
        x=limits[2]-17000;y=limits[1]-2500
        ax.plot([x,x+10000],[y,y],color='#30475c',lw=1.8)
        ax.text(x+5000,y+1300,'10 km',ha='center',fontsize=8,color='#30475c')
        for route,label,offset in [('서해안고속국도','서해안선',(-22,12)),('호남고속국도','호남선',(12,10)),
            ('통영-대전고속국도','통영-대전선',(-35,-12))]:
            line=roads.loc[roads.route_nm.eq(route)].geometry.union_all()
            point=nearest_points(line,line.centroid)[0]
            ax.annotate(label,(point.x,point.y),xytext=offset,textcoords='offset points',fontsize=10,
                color='#30475c',bbox={'facecolor':'white','edgecolor':'none','alpha':.8,'pad':1.2},
                arrowprops={'arrowstyle':'-','color':'#728391','lw':.6})
    handles=[Line2D([0],[0],color=c,lw=3,label=t) for c,t in [('#147f86','취약구간 추정 위치'),
        ('#de9424','목록 밖 노출 확인 후보'),('#8c4b8d','이정 불가')]]
    fig.legend(handles=handles,loc='lower center',ncol=3,fontsize=10,frameon=False,bbox_to_anchor=(.5,.005))
    fig.savefig(destination,dpi=200);plt.close(fig)
    return source


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
            if page==7:ratios=[.30,.22,.22,.26]
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
                height=280 if 'inventory_comparison' in source.name else 156
                scale=min(WIDTH/rect.width,height/rect.height)
                story.extend([Image(str(source),width=rect.width*scale,height=rect.height*scale),Spacer(1,5),
                    Paragraph(html.escape(image.content),styles['small'])])
            else:
                prefix=f'{number}. ' if i>0 and tokens[i-1].type=='list_item_open' else ''
                story.append(Paragraph(prefix+inline(children),styles['body']))
        elif kind=='fence':story.append(Paragraph('<br/>'.join(html.escape(line) for line in token.content.splitlines()),styles['code']))
    assert page==13
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#d8e2e7'));canvas.line(44,38,A4[0]-44,38)
        canvas.setFont('UpdateKR',8);canvas.setFillColor(colors.HexColor('#607380'))
        canvas.drawString(44,24,'icy-road-ai · 분석 기준 2026.10.31 · 비공개 검토본');canvas.drawRightString(A4[0]-44,24,str(doc.page))
    SimpleDocTemplate(str(target),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=40,bottomMargin=50,
        title='미관측 고속도로 구간의 노면온도·결빙 조건과 공식 취약구간 비교',author='icy-road-ai').build(story,onFirstPage=footer,onLaterPages=footer)
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


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=PRIVATE/'report_update_20261031_v3');args=parser.parse_args()
    out=args.output.resolve();assert out.is_relative_to(PRIVATE.resolve())
    if out.exists():raise FileExistsError('Preserve report drafts')
    out.mkdir();frozen=verify_preserved();manuscript=MANUSCRIPT.read_text(encoding='utf8')
    claims,sources=evidence(manuscript)
    figure=ROOT/'docs/images/inventory_comparison_20261031_v3.png'
    if not figure.exists():sources['map_geometry']=map_figure(figure)
    else:sources['map_geometry']=PRIVATE/'vulnerability_map_comparison_20261031_v1/comparison.gpkg'
    sources['map_figure']=figure;sources['manuscript']=MANUSCRIPT;sources['builder']=Path(__file__)
    shutil.copy2(MANUSCRIPT,out/'analysis_report_v8.md')
    pdf=out/'analysis_report_v8.pdf';pages=render(manuscript,pdf)
    preview=out/'preview';preview.mkdir()
    with fitz.open(pdf) as document:
        for i,page in enumerate(document):page.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(preview/f'page_{i+1:02d}.png')
        (out/'extracted_text.txt').write_text('\n'.join(page.get_text() for page in document),encoding='utf8')
    assert verify_preserved()==frozen
    write(out/'build_receipt.json',dict(status='rendered_pending_visual_review',at_utc=now(),pages=pages,claims=claims,
        sources={p.relative_to(ROOT).as_posix():sha(p) for p in sources.values()},
        pdf_sha256=sha(pdf),preservation=frozen,protected_outcomes_read=False))
    print('REPORT RENDERED',pages,pdf,flush=True)


if __name__=='__main__':main()
