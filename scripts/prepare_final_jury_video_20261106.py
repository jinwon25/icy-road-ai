"""복사 가능한 실행 명령과 작은 화면의 표 너비를 실제 데모에도 반영한다."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'scripts/record_polished_jury_demo_20261106.py').read_text('utf8')
assert 'jury_polished_demo_recording' in s and "W/'demo_build_polished.json'" in s
s=s.replace('jury_polished_demo_recording','jury_final_demo_recording').replace("W/'demo_build_polished.json'","W/'demo_build_final.json'")
s=s.replace('validation_weather.parquet\n--output','validation_weather.parquet --output')
# Apply to the inline HTML template only.
s=s.replace('<header><nav class="topnav">','<style>.analysis-grid>div{min-width:0}.table-scroll{max-width:100%}</style><header><nav class="topnav">')
t=ROOT/'scripts/record_final_jury_demo_20261106.py';assert not t.exists();t.write_text(s,'utf8')
