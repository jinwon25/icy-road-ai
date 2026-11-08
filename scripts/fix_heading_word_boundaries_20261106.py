"""짧은 제목에서도 한국어 단어 중간이 갈라지지 않게 한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'outputs/private/late_research_design_20261106/icy_road_model/demo/index.html'
s=p.read_text('utf8');rule='h1,h2,h3{word-break:keep-all;overflow-wrap:break-word;line-break:strict}'
assert rule not in s;s=s.replace('</style>',rule+'</style>');p.write_text(s,'utf8')
