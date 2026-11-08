"""첫 화면은 실제 미리보기로 고정하고 재생 요청 때만 영상을 불러온다."""
from pathlib import Path
import re,json
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/late_research_design_20261106';B=W/'icy_road_model'
def main():
    p=B/'demo/index.html';s=p.read_text('utf8');assert 'id="videoCover"' not in s
    replacement='''<div class="video-shell"><video id="demoVideo" hidden controls preload="none" playsinline poster="poster.png" data-source="model_demo.webm" aria-label="기상 지도부터 전체 기간 추론까지 실제 실행"></video><button id="videoCover" class="video-cover" type="button" aria-controls="demoVideo"><img src="poster.png" alt="실제 실행 영상의 기상 지도 미리보기"><span>영상 재생 · 92초</span></button></div>'''
    s,n=re.subn(r'<video id="demoVideo".*?</video>',replacement,s,count=1);assert n==1
    s=s.replace('</style>','video[hidden],#videoCover[hidden]{display:none!important}.video-cover{position:relative;display:block;border:1px solid var(--line);border-radius:0;padding:0;width:100%;background:white;text-align:left}.video-cover img{width:100%;height:auto;display:block}.video-cover span{position:absolute;bottom:0;left:0;right:0;padding:13px 18px;background:rgba(255,255,255,.97);font-size:15px;color:var(--blue);border-top:1px solid var(--line)}</style>')
    s=s.replace('data-second="9"','data-second="12"').replace('00:09','00:12').replace('data-second="69"','data-second="72"').replace('01:09','01:12')
    script='''<script>const video=document.getElementById('demoVideo'),cover=document.getElementById('videoCover'),buttons=[...document.querySelectorAll('[data-second]')];async function playAt(second){try{cover.hidden=true;video.hidden=false;if(!video.getAttribute('src')){const loaded=new Promise((resolve,reject)=>{video.addEventListener('loadedmetadata',resolve,{once:true});video.addEventListener('error',reject,{once:true})});video.src=video.dataset.source;video.load();await loaded}video.currentTime=second;await video.play();document.getElementById('playbackStatus').textContent='선택한 장면 재생 중';}catch(e){const status=document.getElementById('playbackStatus');status.className='';status.textContent='아래 영상 파일 직접 열기로 재생할 수 있습니다.'}}cover.addEventListener('click',()=>playAt(0));buttons.forEach(b=>b.addEventListener('click',()=>playAt(Number(b.dataset.second))));video.addEventListener('timeupdate',()=>{const current=buttons.filter(b=>Number(b.dataset.second)<=video.currentTime).at(-1);buttons.forEach(b=>{if(b===current)b.setAttribute('aria-current','true');else b.removeAttribute('aria-current')})});window.DEMO_READY=true;</script>'''
    s,n=re.subn(r'<script>.*?</script>',lambda _:script,s,count=1,flags=re.S);assert n==1
    s=s.replace('<a href="inference_log.txt">실행 로그</a>','<a href="inference_log.txt">실행 로그</a><a href="model_demo.webm">영상 파일 직접 열기</a>')
    p.write_text(s,'utf8')
    p=W/'frontend_build.json';v=json.loads(p.read_text('utf8'))
    for c in v['chapters']:
        if c['second']==9:c['second']=12
        elif c['second']==69:c['second']=72
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
if __name__=='__main__':main()
