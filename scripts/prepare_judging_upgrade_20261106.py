"""추가 검토의 공개 참고자료와 10개 겨울 ASOS 기후 조회를 준비한다."""
from pathlib import Path
import sys,json
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.kma_rwis_download import load_auth_key
P=ROOT/'outputs/private';W=P/'judging_upgrade_20261106'
W.mkdir(exist_ok=True);R=W/'references';R.mkdir(exist_ok=True)
sources={
'critical_skill.md':'https://raw.githubusercontent.com/K-Dense-AI/scientific-agent-skills/main/skills/scientific-critical-thinking/SKILL.md',
'visualization_skill.md':'https://raw.githubusercontent.com/K-Dense-AI/scientific-agent-skills/main/skills/scientific-visualization/SKILL.md',
'figure_guidelines.md':'https://raw.githubusercontent.com/K-Dense-AI/scientific-agent-skills/main/skills/scientific-visualization/references/publication_guidelines.md',
'critical_review_sources.md':'https://raw.githubusercontent.com/K-Dense-AI/scientific-agent-skills/main/skills/scientific-critical-thinking/references/review_sources.md',
'LICENSE.txt':'https://raw.githubusercontent.com/K-Dense-AI/scientific-agent-skills/main/LICENSE'}
lines=['parallel','parallel-max = 3','connect-timeout = 10','max-time = 40','fail']
for name,url in sources.items():
 lines+=['url = '+json.dumps(url),'output = '+json.dumps((R/name).relative_to(ROOT).as_posix())]
(W/'references.curl').write_text('\n'.join(lines)+'\n','utf8')
(R/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n','utf8')
m=json.loads((P/'submission_candidate_20261106_v14/data/prediction_group_manifest.json').read_text('utf8'))
ids=sorted({int(v['asos_station']) for v in m.values()})
params=dict(tm1='20161101',tm2='20161130',stn=':'.join(map(str,ids)),help='1',authKey=load_auth_key(ROOT/'secret.env'))
url='https://apihub.kma.go.kr/api/typ01/url/kma_sfcdd3.php?'+urlencode(params)
(W/'climate_probe.secret.curl').write_text('connect-timeout = 10\nmax-time = 50\nfail\nurl = '+json.dumps(url)+'\noutput = '+json.dumps((W/'climate_probe.txt').relative_to(ROOT).as_posix())+'\n','utf8')
(W/'climate_scope.json').write_text(json.dumps(dict(stations=ids,first_winter=2016,last_winter=2025,months=[11,12,1,2],only_atmospheric_observations=True,road_outcomes_read=False),indent=2)+'\n','utf8')
print('Prepared climate stations',ids,'and',len(sources),'public references')

if False: pass
