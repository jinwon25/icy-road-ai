"""공식 문제 본문에 내장된 그림을 변환 없이 추출해 출처와 해시를 보존한다."""
import base64
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=ROOT/'outputs/private/official_research_review_20261031_v1/problem_tab_contents.json'
    out=ROOT/'outputs/private/official_problem_figures_20261031_v1'
    out.mkdir(parents=True,exist_ok=False)
    records=[]
    for section in json.loads(source.read_text(encoding='utf-8')):
        for name,kind,encoded in re.findall(r'!\[([^\]]*)\]\(data:image/([^;]+);base64,([A-Za-z0-9+/=\s]+)\)',section['content']):
            assert kind in ['jpeg','png']
            data=base64.b64decode(encoded,validate=True)
            file=f'figure_{len(records)+1:02d}.'+('jpg' if kind=='jpeg' else 'png')
            (out/file).write_bytes(data)
            records.append(dict(file=file,source_title=section['title'],original_name=name,
                bytes=len(data),sha256=sha256(data).hexdigest()))
    (out/'receipt.json').write_text(json.dumps(dict(source_sha256=sha256(source.read_bytes()).hexdigest(),
        original_bytes_preserved=True,figures=records),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(records,ensure_ascii=False))


if __name__=='__main__':main()
