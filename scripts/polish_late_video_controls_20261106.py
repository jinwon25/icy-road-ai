"""첫 재생 전에는 미리보기를 유지하고, 실제 장면 경계에 맞춰 이동한다."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model'
def main():
    p=B/'demo/index.html';s=p.read_text('utf8');assert s.count('preload="metadata"')==1
    s=s.replace('preload="metadata"','preload="none"').replace('data-second="65"','data-second="69"').replace('01:05','01:09').replace('data-second="83"','data-second="86"').replace('01:23','01:26')
    old="try{video.currentTime=Number(b.dataset.second);await video.play();"
    new="try{if(video.readyState<1){video.preload='auto';video.load();await new Promise((resolve,reject)=>{video.addEventListener('loadedmetadata',resolve,{once:true});video.addEventListener('error',reject,{once:true})})}video.currentTime=Number(b.dataset.second);await video.play();"
    assert old in s;s=s.replace(old,new);p.write_text(s,'utf8')
    p=W/'frontend_build.json';v=json.loads(p.read_text('utf8'))
    for c in v['chapters']:
        if c['second']==65:c['second']=69
        elif c['second']==83:c['second']=86
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
if __name__=='__main__':main()
