"""GFM을 로컬에서 렌더하고 상대 링크·앵커·표·의도하지 않은 마크업을 검사한다."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import unicodedata
from urllib.parse import unquote, urlsplit

from cmarkgfm import github_flavored_markdown_to_html
from cmarkgfm.cmark import Options

ROOT = Path(__file__).resolve().parents[1]


class Rendered(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links, self.anchors, self.errors = [], set(), []
        self.heading = None
        self.heading_text = []
        self.slug_counts = Counter()
        self.code_depth = 0
        self.row = None
        self.table_columns = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.anchors.add(attrs['id'])
        if tag in ('a', 'img'):
            self.links.append(attrs.get('href' if tag == 'a' else 'src', ''))
        if tag in ('code', 'pre'):
            self.code_depth += 1
        if re.fullmatch('h[1-6]', tag):
            self.heading, self.heading_text = tag, []
        if tag == 'del':
            self.errors.append('의도하지 않은 취소선: 범위 표기를 확인하세요')
        if tag == 'table':
            self.table_columns = None
        if tag == 'tr':
            self.row = 0
        if tag in ('td', 'th') and self.row is not None:
            self.row += 1

    def handle_endtag(self, tag):
        if tag in ('code', 'pre'):
            self.code_depth -= 1
        if tag == self.heading:
            text = ''.join(self.heading_text).lower()
            slug = ''.join(c for c in text if c in '-_' or not unicodedata.category(c).startswith(('P', 'S', 'C')))
            slug = slug.replace(' ', '-')
            count = self.slug_counts[slug]
            self.slug_counts[slug] += 1
            self.anchors.add(slug + (f'-{count}' if count else ''))
            self.heading = None
        if tag == 'tr' and self.row is not None:
            if self.table_columns is None:
                self.table_columns = self.row
            elif self.row != self.table_columns:
                self.errors.append('렌더된 표의 열 수 불일치')
            self.row = None

    def handle_data(self, data):
        if self.heading:
            self.heading_text.append(data)
        if not self.code_depth and '**' in data:
            self.errors.append('원시 굵게 마크업 노출: ** 구문을 확인하세요')


def inspect_documents(root, names, render_dir=None):
    root = root.resolve()
    rendered, errors = {}, []
    for name in names:
        path = root / name
        source = path.read_text(encoding='utf-8-sig')
        html = github_flavored_markdown_to_html(source, options=Options.CMARK_OPT_UNSAFE)
        rendered[path.resolve()] = Rendered(html)
        # GFM은 넘친 표 열을 버릴 수 있으므로 원문의 구분자 수도 대조한다.
        lines = source.splitlines()
        in_fence, expected_columns = False, None
        for i, line in enumerate(lines):
            if line.lstrip().startswith(('```', '~~~')):
                in_fence = not in_fence
                expected_columns = None
            if in_fence:
                continue
            stripped = line.strip()
            if not stripped.startswith('|'):
                expected_columns = None
                continue
            columns = len(re.split(r'(?<!\\)\|', stripped.strip('|')))
            if expected_columns is None and i + 1 < len(lines) and re.fullmatch(r'[|\s:\-]+', lines[i + 1]):
                expected_columns = columns
            if expected_columns is not None and columns != expected_columns:
                rendered[path.resolve()].errors.append(f'{i + 1}행: 원문 표의 열 수 불일치')
        if render_dir:
            target = render_dir / Path(name).with_suffix('.html')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('<!doctype html><meta charset="utf-8"><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;line-height:1.65}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:8px}pre{white-space:pre-wrap;background:#eee;padding:16px}img{max-width:100%}</style>' + html, encoding='utf-8')
    for path, doc in rendered.items():
        errors.extend(f'{path.relative_to(root)}: {e}' for e in doc.errors)
        for link in doc.links:
            parts = urlsplit(link)
            if parts.scheme or parts.netloc:
                continue
            target = (path.parent / unquote(parts.path)).resolve() if parts.path else path
            if not target.is_relative_to(root.resolve()) or not target.exists():
                errors.append(f'{path.relative_to(root)}: 상대 링크 누락/이탈 -> {link}')
            elif parts.fragment and target in rendered and unquote(parts.fragment) not in rendered[target].anchors:
                errors.append(f'{path.relative_to(root)}: 앵커 누락 -> {link}')
    return errors


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render-dir', type=Path)
    parser.add_argument('--include-untracked', action='store_true', help='새 Markdown도 Git 제외 규칙에 따라 함께 검사한다.')
    args = parser.parse_args()
    command = ['git', 'ls-files', '-z']
    if args.include_untracked:
        command += ['--cached', '--others', '--exclude-standard']
    names = subprocess.check_output(command + ['*.md'], cwd=ROOT).decode('utf-8').split('\0')
    names = list(filter(None, names))
    # 문서 이동 후 커밋 전에도 현재 작업 트리를 검증한다.
    if args.include_untracked:
        names = [name for name in names if (ROOT / name).is_file()]
    if args.render_dir and not args.render_dir.resolve().is_relative_to((ROOT / 'outputs/private').resolve()):
        parser.error('렌더 결과는 outputs/private 내부에 저장하세요.')
    errors = inspect_documents(ROOT, names, args.render_dir)
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Markdown {len(names)}개 로컬 GFM 렌더·상대 링크·앵커 검사 통과')


if __name__ == '__main__':
    main()
