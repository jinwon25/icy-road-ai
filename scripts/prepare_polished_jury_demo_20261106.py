"""전체 실행값은 보존하고 화면의 결측 표기·단위·모바일 표를 읽기 쉽게 정리한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def swap(s,a,b):assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
def main():
    s=(ROOT/'scripts/record_jury_demo_20261106.py').read_text('utf8')
    s=swap(s,'assert not output.exists()','assert output.exists()')
    a=" run=subprocess.run(cmd,cwd=B,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180);assert run.returncode==0\n (O/'inference_log.txt').write_bytes(run.stdout)"
    b=" stdout=(O/'inference_log.txt').read_bytes();assert json.loads(stdout.decode('utf8'))['rows']==103680"
    s=swap(s,a,b).replace("stats=json.loads(run.stdout.decode('utf8').strip())","stats=json.loads(stdout.decode('utf8').strip())")
    a=" stats=json.loads(stdout.decode('utf8').strip())"
    b=""" shown['추정 노면온도 (°C)']=shown['추정 노면온도 (°C)'].map(lambda x:'미산출' if pd.isna(x) else f'{x:.2f}')
 shown['결빙 판정']=shown['결빙 판정'].map(lambda x:'미산출' if pd.isna(x) else str(int(x)))
 shownin=shownin.rename(columns={'station':'지점','time':'시각 (KST)','asos_air_temp':'ASOS 기온 (°C)','aws_air_temp':'AWS 기온 (°C)','aws_humidity':'AWS 습도 (%)'})
 for col in ['ASOS 기온 (°C)','AWS 기온 (°C)','AWS 습도 (%)']:shownin[col]=shownin[col].map(lambda x:'입력 없음' if pd.isna(x) else f'{x:.1f}')
 stats=json.loads(stdout.decode('utf8').strip())"""
    s=swap(s,a,b)
    s=s.replace('포함된 예제 기상을 로컬 Python 모형에 입력해 생성한 결과입니다.','두 겨울의 전체 검증 기상을 로컬 Python 모형에 입력한 결과입니다. 입력 조건이 부족한 시각은 미산출로 남겼습니다.')
    s=s.replace('<div><h3>입력 예시</h3>__INPUT__</div><div><h3>추정 결과</h3>__OUTPUT__</div>',
        '<div><h3>입력 일부</h3><div class="table-scroll">__INPUT__</div></div><div><h3>추정 결과 일부</h3><div class="table-scroll">__OUTPUT__</div></div>')
    s=s.replace("str(stats['rows'])","f\"{stats['rows']:,}\"").replace("str(stats['road_temperature_available'])","f\"{stats['road_temperature_available']:,}\"").replace("str(stats['ice_available'])","f\"{stats['ice_available']:,}\"")
    s=s.replace('recording=W/\'team_demo_recording\'','recording=W/\'jury_polished_demo_recording\'')
    s=s.replace("W/'demo_build_team.json'","W/'demo_build_polished.json'")
    target=ROOT/'scripts/record_polished_jury_demo_20261106.py';assert not target.exists();target.write_text(s,'utf8')
    s=(ROOT/'scripts/audit_jury_media_20261106.py').read_text('utf8').replace("O=W/'media_review_jury'","O=W/'media_review_polished'")
    (ROOT/'scripts/audit_polished_jury_media_20261106.py').write_text(s,'utf8')
if __name__=='__main__':main()
