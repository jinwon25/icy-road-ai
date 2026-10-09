"""실제 GFM 렌더 결과에서 잘못된 앵커·취소선·굵게 노출을 찾아낸다."""
from pathlib import Path
import tempfile
import unittest
from scripts.check_markdown import inspect_documents


class MarkdownTests(unittest.TestCase):
    def test_korean_duplicate_anchors_and_escaped_table_pipe(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'a.md').write_text('# 한글 제목\n\n## 한글 제목\n\n[x](#한글-제목-1)\n\n| 값 | 설명 |\n|---|---|\n| `a\\|b` | 좋음 |\n', encoding='utf-8')
            self.assertEqual(inspect_documents(root, ['a.md']), [])

    def test_bad_link_anchor_strike_and_bold_exposure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'a.md').write_text('# 제목\n\n[x](#없음) [y](missing.md)\n\n1~~2~~3\n\n**(내용)**입니다\n', encoding='utf-8')
            errors = inspect_documents(root, ['a.md'])
            for phrase in ['앵커 누락', '상대 링크 누락', '취소선', '마크업 노출']:
                self.assertTrue(any(phrase in e for e in errors), (phrase, errors))


if __name__ == '__main__':
    unittest.main()
