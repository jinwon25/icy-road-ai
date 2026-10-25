"""한 Markdown 원고와 봉인된 집계에서 검토용 한글 PDF·그림을 생성한다."""
import argparse
import html
import json
from pathlib import Path
import shutil
import sys

import fitz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from markdown_it import MarkdownIt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file as sha
from scripts.blind_icing_validation import read, write, now, old_freezes, verify, DEFAULT

MANUSCRIPT = ROOT / 'docs/delivery/ANALYSIS_REPORT.md'
OLD = ROOT / 'outputs/private/submission_candidate_20261025_v6'
WIDTH = A4[0] - 88


def load_evidence():
    sources = {
        'selection': OLD / 'research/extended/selection.json',
        'ice': OLD / 'research/extended/audit.json',
        'baseline': ROOT / 'outputs/private/two_winter_models_20261024_v1/summary.json',
        'comparison': ROOT / 'outputs/private/extended_completion_20261024_v1/summary.json',
        'blind': DEFAULT / 'summary.json',
    }
    data = {key: read(path) for key, path in sources.items()}
    assert data['selection']['status'] == 'audited_final_selection'
    assert not data['blind']['primary_success']
    verify(DEFAULT)
    assert old_freezes() == (47, 549)
    return data, sources


def check_claims(manuscript, data):
    """보고서 핵심 수치를 기존 집계에 연결한다. 성능을 다시 평가하지 않는다."""
    selected = data['selection']['temperature_report']
    current = data['ice']['physical']['both']
    baseline = data['comparison']['classification']['terrain_classification_20261024_v1']['reports']['asos_zero']
    values = {}
    for key, value in selected['regression']['pooled'].items():
        values['temperature_' + key] = f'{value:,}' if key == 'n' else f'{value:.6f}'
    old = data['baseline']['regression']['all']['both']['pooled']['mae']
    values['old_mae'] = f'{old:.6f}'
    values['mae_gain_percent'] = f"{100 * (1 - selected['regression']['pooled']['mae'] / old):.2f}%"
    for scope in ['all', '2024', '2025']:
        values['ice_' + scope] = f"{current[scope]['f1_fixed_population']:.6f}"
        values['air_' + scope] = f"{baseline[scope]['f1_fixed_population']:.6f}"
    for key, report in data['blind']['reports'].items():
        for metric in ['f1_fixed_population', 'recall_available_station_mean']:
            values[key + '_' + metric] = f'{report["144"][metric]:.6f}'
    for label, value in values.items():
        assert value in manuscript, (label, value)
    return values


def figures(data):
    destination = ROOT / 'docs/images'
    plt.rcParams.update({'font.family': 'Malgun Gothic', 'axes.unicode_minus': False, 'font.size': 10})
    selected = data['selection']['temperature_report']
    old = data['baseline']['regression']['all']['both']
    labels = ['두 겨울 통합', '2024/25', '2025/26', '관측 -2~2°C']
    a = [old['pooled']['mae'], *[selected['winters'][y]['baseline']['pooled']['mae'] for y in ['2024', '2025']], old['near_freezing']['mae']]
    b = [selected['regression']['pooled']['mae'], *[selected['winters'][y]['new']['pooled']['mae'] for y in ['2024', '2025']], selected['regression']['near_freezing']['mae']]
    fig, ax = plt.subplots(figsize=(9.4, 2.6), layout='constrained')
    for values, offset, color, label in [(a, -.18, '#a8b7c5', '기존 모델'), (b, .18, '#147f86', '이력 확장')]:
        bars = ax.barh([i + offset for i in range(4)], values, height=.33, color=color, label=label)
        ax.bar_label(bars, fmt='%.3f', padding=3, fontsize=9)
    ax.set_yticks(range(4), labels); ax.invert_yaxis(); ax.set_xlim(0, 1.75)
    ax.set_xlabel('MAE (°C)'); ax.legend(loc='upper right', frameon=False)
    ax.spines[['top', 'right']].set_visible(False)
    fig.savefig(destination / 'editorial_temperature_20261025.png', dpi=180); plt.close(fig)
    reports = data['blind']['reports']
    fig, axes = plt.subplots(1, 3, figsize=(9.4, 2.0), layout='constrained')
    for ax, key, title in zip(axes, ['tp', 'fp', 'fn'], ['맞힌 결빙 TP', '오경보 FP', '미탐 FN']):
        values = [reports[name]['144'][key] for name in ['asos_zero', 'logit_day_anchor1']]
        bars = ax.bar(['기온 기준선', '주 후보'], values, color=['#a8b7c5', '#147f86'])
        ax.bar_label(bars, labels=[f'{v:,}' for v in values], padding=3, fontsize=10)
        ax.set_ylim(0, max(values) * 1.35); ax.set_title(title, fontsize=11); ax.set_ylabel('행 수')
        ax.spines[['top', 'right']].set_visible(False)
    fig.savefig(destination / 'editorial_blind_20261025.png', dpi=180); plt.close(fig)
    source = OLD / 'figures/candidate_condition_map_500m.jpg'
    target = destination / 'editorial_condition_map_20261025.jpg'
    if target.exists():
        assert sha(target) == sha(source)
    else:
        shutil.copy2(source, target)


def inline(tokens):
    """원고의 문장을 그대로 조판하고 외부 링크만 PDF 링크로 만든다."""
    parts = []; links = []
    for token in tokens or []:
        kind = token.type
        if kind in {'text', 'code_inline'}:
            parts.append(html.escape(token.content))
        elif kind in {'softbreak', 'hardbreak'}:
            parts.append(' ' if kind == 'softbreak' else '<br/>')
        elif kind == 'strong_open': parts.append('<b>')
        elif kind == 'strong_close': parts.append('</b>')
        elif kind == 'em_open': parts.append('<i>')
        elif kind == 'em_close': parts.append('</i>')
        elif kind == 'link_open':
            href = token.attrGet('href') or ''
            external = href.startswith(('https://', 'http://')); links.append(external)
            if external: parts.append('<link href="' + html.escape(href, quote=True) + '" color="#147f86">')
        elif kind == 'link_close':
            if links.pop(): parts.append('</link>')
        else:
            raise ValueError('Unsupported inline token: ' + kind)
    assert not links
    return ''.join(parts)


def render(manuscript, target):
    pdfmetrics.registerFont(TTFont('ReportKR', 'C:/Windows/Fonts/malgun.ttf'))
    pdfmetrics.registerFont(TTFont('ReportKRBold', 'C:/Windows/Fonts/malgunbd.ttf'))
    pdfmetrics.registerFontFamily('ReportKR', normal='ReportKR', bold='ReportKRBold', italic='ReportKR', boldItalic='ReportKRBold')
    navy = colors.HexColor('#20394c'); teal = colors.HexColor('#147f86')
    styles = {key: ParagraphStyle(key, fontName='ReportKRBold' if key in ['h1', 'h2', 'h3'] else 'ReportKR',
                fontSize=size, leading=leading, wordWrap='CJK', textColor=navy, spaceAfter=space,
                keepWithNext=key in ['h1', 'h2', 'h3'])
              for key, size, leading, space in [('h1', 23, 32, 12), ('h2', 17, 24, 12), ('h3', 11.5, 17, 7),
                                                 ('body', 9.6, 15.7, 9), ('small', 8.2, 12.3, 6), ('code', 8, 12, 8)]}
    story = []; headings = []; table_rows = []; row = []; in_table = False; page = 1
    list_number = 0
    tokens = MarkdownIt('commonmark').enable('table').parse(manuscript)
    for i, token in enumerate(tokens):
        kind = token.type
        if kind == 'html_block':
            assert token.content.strip() == '<!-- page -->'
            story.append(PageBreak()); page += 1
        elif kind == 'heading_open':
            content = tokens[i + 1]
            heading = inline(content.children)
            if token.tag == 'h1':
                heading = heading.replace('구간의 ', '구간의<br/>', 1)
            story.append(Paragraph(heading, styles[token.tag]))
            if token.tag in {'h1', 'h2'}: headings.append((page, content.content))
        elif kind == 'table_open': in_table = True; table_rows = []
        elif kind == 'tr_open': row = []
        elif kind == 'inline' and in_table: row.append(Paragraph(inline(token.children), styles['small']))
        elif kind == 'tr_close': table_rows.append(row)
        elif kind == 'table_close':
            in_table = False
            n = len(table_rows[0]); ratios = {2: [.32, .68], 3: [.29, .34, .37], 4: [.40, .20, .20, .20]}[n]
            if page == 4: ratios = [.48, .26, .26]
            table = Table(table_rows, colWidths=[WIDTH * w for w in ratios], repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e7f0f1')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, 0), .65, teal),
                ('LINEBELOW', (0, 1), (-1, -1), .25, colors.HexColor('#dce4e8')),
                ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
                ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
            story.extend([table, Spacer(1, 9)])
        elif kind == 'ordered_list_open': list_number = 0
        elif kind == 'list_item_open': list_number += 1
        elif kind == 'paragraph_open' and not in_table:
            content = tokens[i + 1]
            children = content.children or []
            if len(children) == 1 and children[0].type == 'image':
                item = children[0]; source = (MANUSCRIPT.parent / item.attrGet('src')).resolve()
                image_doc = fitz.open(source); rect = image_doc[0].rect
                max_height = 272 if source.suffix == '.jpg' else 156
                scale = min(WIDTH / rect.width, max_height / rect.height)
                story.append(Image(str(source), width=rect.width * scale, height=rect.height * scale))
                story.extend([Spacer(1, 5), Paragraph(html.escape(item.content), styles['small'])])
            else:
                prefix = f'{list_number}. ' if i > 0 and tokens[i - 1].type == 'list_item_open' else ''
                story.append(Paragraph(prefix + inline(children), styles['body']))
        elif kind == 'fence':
            story.append(Paragraph('<br/>'.join(html.escape(line) for line in token.content.splitlines()), styles['code']))
    assert page == 10
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor('#d8e2e7')); canvas.line(44, 38, A4[0] - 44, 38)
        canvas.setFont('ReportKR', 8); canvas.setFillColor(colors.HexColor('#607380'))
        canvas.drawString(44, 24, 'icy-road-ai · 분석 기준 2026.10.25 · 비공개 검토본')
        canvas.drawRightString(A4[0] - 44, 24, str(doc.page))
    SimpleDocTemplate(str(target), pagesize=A4, leftMargin=44, rightMargin=44, topMargin=40, bottomMargin=50,
        title='미관측 고속도로 구간의 노면온도 추정과 결빙 탐지', author='icy-road-ai').build(story, onFirstPage=footer, onLaterPages=footer)
    document = fitz.open(target)
    assert len(document) == page, f'Page overflow: {len(document)} != {page}'
    for number, heading in headings:
        expected = ''.join(heading.split())
        actual = ''.join(document[number - 1].get_text().split())
        assert expected in actual, ('Heading shifted', number, heading)
    for p in document:
        assert '\x00' not in p.get_text()
        for block in p.get_text('dict')['blocks']:
            if block['type'] == 0:
                for line in block['lines']:
                    for span in line['spans']:
                        x0, y0, x1, y1 = span['bbox']
                        assert x0 >= 40 and x1 <= A4[0] - 39 and y0 >= 34 and y1 <= A4[1] - 18, span['text']
    return len(document)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Use a new report directory')
    data, sources = load_evidence()
    manuscript = MANUSCRIPT.read_text(encoding='utf8')
    claims = check_claims(manuscript, data)
    figures(data)
    args.output.mkdir(parents=True)
    target = args.output / 'analysis_report_v7.pdf'
    pages = render(manuscript, target)
    shutil.copy2(MANUSCRIPT, args.output / 'ANALYSIS_REPORT.md')
    inputs = [MANUSCRIPT, Path(__file__), *sources.values(), *sorted((ROOT / 'docs/images').glob('editorial_*20261025.*'))]
    write(args.output / 'receipt.json', dict(status='created_pending_visual_review', at_utc=now(), pages=pages,
        pdf_sha256=sha(target), manuscript_sha256=sha(MANUSCRIPT), checked_claims=claims,
        source_hashes={p.relative_to(ROOT).as_posix(): sha(p) for p in inputs}))
    print(json.dumps({'pdf': str(target), 'pages': pages, 'checked_claims': len(claims)}, ensure_ascii=False))


if __name__ == '__main__': main()
