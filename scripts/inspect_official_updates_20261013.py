"""공식 숨김 답변·내장 이미지·HWP 본문을 추출하고 과거 본문과 비교한다."""
import base64
import difflib
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/private/official_updates_20261013_v1'
sys.path.insert(0, str(ROOT / 'outputs/private/official_review_20261007/tools'))
import olefile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def paragraph_text(payload):
    result = []; position = 0
    while position+2 <= len(payload):
        code = struct.unpack_from('<H', payload, position)[0]
        if code >= 32:
            result.append(payload[position:position+2].decode('utf-16le', errors='replace')); position += 2
        elif code in (10, 13):
            result.append('\n'); position += 2
        elif code in (0, 24, 25, 30, 31):
            result.append(' '); position += 2
        else:
            result.append(' '); position += 16
    return ''.join(result)


def hwp_text(path):
    paragraphs = []; sections = []; preview = ''
    with olefile.OleFileIO(path) as document:
        header = document.openstream('FileHeader').read()
        properties = struct.unpack_from('<I', header, 36)[0]
        if properties & (2|4):
            raise ValueError('Encrypted or distribution HWP not supported')
        if document.exists('PrvText'):
            preview = document.openstream('PrvText').read().decode('utf-16le', errors='replace')
        for name in document.listdir():
            if len(name) != 2 or name[0] != 'BodyText' or not name[1].startswith('Section'):
                continue
            data = document.openstream(name).read()
            if properties & 1:
                data = zlib.decompress(data, -15)
            offset = 0; records = 0
            while offset+4 <= len(data):
                header = struct.unpack_from('<I', data, offset)[0]; offset += 4
                tag, length = header & 0x3ff, header >> 20
                if length == 0xfff:
                    length = struct.unpack_from('<I', data, offset)[0]; offset += 4
                if offset+length > len(data):
                    raise ValueError('Truncated HWP body record')
                payload = data[offset:offset+length]; offset += length; records += 1
                if tag == 67:
                    paragraphs.append(paragraph_text(payload))
            if offset != len(data):
                raise ValueError('Unparsed HWP section tail')
            sections.append(dict(stream='/'.join(name), bytes=len(data), records=records))
    return '\n'.join(paragraphs), preview, sections


def extract_body(name):
    soup = BeautifulSoup((OUT / (name+'.html')).read_bytes(), 'html.parser'); bodies = {}
    for node in soup.select('input[id]'):
        identifier = node['id']
        if identifier in ('nttCn', 'reply_nttCn') or identifier.startswith('commentCn'):
            bodies[identifier] = str(node.get('value', ''))
    images = []
    for identifier, content in bodies.items():
        def replace(match):
            raw = base64.b64decode(match.group(2))
            suffix = '.png' if raw.startswith(b'\x89PNG') else '.jpg' if raw.startswith(b'\xff\xd8') else '.bin'
            image = OUT / f'{name}_{identifier}_image_{len(images)}{suffix}'; image.write_bytes(raw)
            images.append(dict(file=image.name, bytes=len(raw), sha256=sha(raw), mime_type=match.group(1)))
            return image.name
        content = re.sub(r'data:(image/[A-Za-z0-9.+-]+);base64,([A-Za-z0-9+/=\r\n]+)', replace, content)
        (OUT / (name+'_'+identifier+'_clean.md')).write_text(content, encoding='utf-8')
    return dict(fields={k: dict(characters=len(v), sha256=sha(v.encode())) for k, v in bodies.items()}, images=images)


def main():
    target = OUT / 'change_comparison.json'
    if target.exists():
        raise FileExistsError('Preserve completed comparison')
    extraction = {}
    for path in OUT.glob('*.html'):
        if path.stem.startswith(('notice_', 'general_qa_', 'problem_qa_')) and path.stem != 'notice_list':
            extraction[path.stem] = extract_body(path.stem)
    current = json.loads((OUT / 'problem_tabs.bin').read_bytes())
    previous = json.loads((ROOT / 'outputs/private/official_review_20261007/overview_live.json').read_text('utf-8'))
    tabs = []
    for i, item in enumerate(current['overviewList']):
        content = item['content']; prior = previous['overviewList'][i]['content']
        (OUT / f'tab_{i}_body.md').write_text(content, encoding='utf-8')
        tabs.append(dict(index=i, title=item.get('title'), modify_date=item.get('modifyDt'), sha256=sha(content.encode()), old_sha256=sha(prior.encode()),
                         exact_content_equal=content == prior, normalized_content_equal=re.sub(r'\s+', ' ', content) == re.sub(r'\s+', ' ', prior)))
    app = OUT / 'current_application.hwp'; old = ROOT / 'outputs/private/ice_methodology_references_20261010_v1/official_pledge.bin'
    texts = {}
    for label, path in [('new', app), ('old', old)]:
        text, preview, sections = hwp_text(path); texts[label] = text
        (OUT / f'application_{label}_body.txt').write_text(text, encoding='utf-8')
        (OUT / f'application_{label}_preview.txt').write_text(preview, encoding='utf-8')
        extraction['application_'+label] = dict(bytes=path.stat().st_size, sha256=sha(path.read_bytes()), text_sha256=sha(text.encode()), sections=sections)
    changes = '\n'.join(difflib.unified_diff(texts['old'].splitlines(), texts['new'].splitlines(), fromfile='application_before_20261010', tofile='application_current_20261013', lineterm=''))
    (OUT / 'application_body_diff.txt').write_text(changes, encoding='utf-8')
    comparison = dict(tabs=tabs, extracted=extraction, application_bytes_equal=app.read_bytes() == old.read_bytes(),
                      application_text_equal=re.sub(r'\s+', '', texts['old']) == re.sub(r'\s+', '', texts['new']), application_diff_file='application_body_diff.txt')
    target.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(tabs=tabs, application_bytes_equal=comparison['application_bytes_equal'], application_text_equal=comparison['application_text_equal'],
                         faq_images=extraction['notice_639']['images'], hwp_sizes={k: extraction['application_'+k]['bytes'] for k in ['old', 'new']}), ensure_ascii=False))
    print('FAQ CLEAN:', (OUT / 'notice_639_nttCn_clean.md').read_text('utf-8')[:10000])
    for name in ['general_qa_632', 'general_qa_618']:
        print(name, (OUT / (name+'_reply_nttCn_clean.md')).read_text('utf-8'))
    print('APPLICATION DIFF:', changes[:10000])


if __name__ == '__main__':
    main()
