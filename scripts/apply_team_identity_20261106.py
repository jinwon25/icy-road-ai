"""로드투인사이트 팀명을 최종 보고서·화면·실행 안내에 반영한다."""
from pathlib import Path
import re,shutil
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/judging_upgrade_20261106';B=W/'icy_road_model';O=W/'information_group_correction'
team='로드투인사이트'
p=ROOT/'scripts/build_information_report_20261106.py';s=p.read_text('utf8')
s=s.replace("author='icy-road-ai'","author='로드투인사이트'")
s=s.replace("p('2026 DATA·AI 분석 경진대회  문제해결 부문","p('로드투인사이트 / 2026 DATA·AI 분석 경진대회  문제해결 부문")
s=s.replace("c.drawString(44,23,'전북 고속도로 겨울철 분석')","c.drawString(44,23,'로드투인사이트 / 전북 고속도로 겨울철 분석')")
s=s.replace("RWIS의 노면온도·노면상태와 도로 기상 관측. 회귀·분류 평가의 기준값","제공 17지점 중 학습14·검증3. 공개 RWIS 9지점 추가[11]")
s=s.replace("노면온도는 기상·과거 이력·태양위치 63특성을 입력한 HistGradientBoosting 회귀로 추정했다.",
    "노면온도는 학습 허용 23지점의 유효 관측쌍 793,149개로 기상·이력·태양위치 63특성의 HistGradientBoosting 회귀를 학습했다.")
s=s.replace("('https://gml.noaa.gov/grad/solcalc/calcdetails.html')]","('https://gml.noaa.gov/grad/solcalc/calcdetails.html')]") if False else s
old="('[10] NOAA GML. Solar Calculation Details. 태양위치 근사식의 범위.','https://gml.noaa.gov/grad/solcalc/calcdetails.html')]"
new="('[10] NOAA GML. Solar Calculation Details. 태양위치 근사식의 범위.','https://gml.noaa.gov/grad/solcalc/calcdetails.html'),\n ('[11] 기상청 API허브. 추가 도로기상 관측·지점 정보의 원천.','https://apihub.kma.go.kr/apiInfo.do')]"
assert old in s;s=s.replace(old,new);p.write_text(s,'utf8')
for original,saved in [(B/'report/analysis_report.pdf',O/'report_before_team_name.pdf'),(W/'report_build.json',O/'report_build_before_team_name.json')]:
    assert original.resolve().is_relative_to(W.resolve()) and saved.resolve().is_relative_to(W.resolve()) and not saved.exists()
    original.replace(saved)
css=B/'assets/site.css'
css.write_text(css.read_text('utf8')+'\n.topnav .team-brand{font-size:15px;font-weight:700;color:var(--ink);margin-right:auto;border-bottom:0;text-decoration:none}@media(max-width:720px){.topnav .team-brand{flex-basis:100%;font-size:15px;margin-bottom:1px}}\n','utf8')
def brand(text,href):
    return re.sub(r'(<nav class="topnav"[^>]*>)',lambda m:m.group(1)+'<a class="team-brand" href="'+href+'">로드투인사이트</a>',text)
for relative in ['index.html','demo/index.html','demo/inference.html']:
    p=B/relative;p.write_text(brand(p.read_text('utf8'),'index.html' if relative=='index.html' else '../index.html'),'utf8')
p=ROOT/'src/templates/inspection_evidence.html';p.write_text(brand(p.read_text('utf8'),'../index.html'),'utf8')
shutil.copyfile(p,B/'assets/inspection_template.txt')
p=B/'README.md';s=p.read_text('utf8').replace('# 전북 고속도로 겨울철 분석\n','# 전북 고속도로 겨울철 분석\n\n참가팀: **로드투인사이트**\n',1)
s=s.replace('Python 3.11·CPU에서 실행한다.','Windows 64비트·Python 3.11·CPU에서 검증했다.')
p.write_text(s,'utf8')
(B/'AI_USAGE.md').write_text('''# AI 활용 및 주요 검토

참가팀: **로드투인사이트**

OpenAI Codex를 문제·자료 검토, 데이터 처리와 모형·평가 코드, 실험 실행, 결과 해석, 보고서 조판, 오프라인 지도와 데모 제작에 활용했다. 팀이 제시한 방향은 결빙 정밀도 검토, 최신 규정 반영, 최종 결과 중심의 문서·화면, 심사자 관점의 객관적 보완이다. 코드 실행·계산·시각 검수는 AI 지원으로 수행한 범위를 기준으로 기재했다.

## 대안과 최종 선택

기온·적설 등 ASOS 이력 확장, 노면상태의 다중 분류, 가까운 AWS와 실제 DSM의 국소 입력, 적설 증가 경과 규칙을 비교했다. 개발 지역을 제외한 예측에서 정밀도·F1·재현율과 결빙 사건 보존 조건을 함께 확인했으며, 추가 후보가 채택 조건을 충족하지 못했다. 적설 경과 조건은 오경보를 줄이면서 일부 실제 결빙 사건도 잃었다. 현재 결빙 판정 모형은 유지했다.

현재 노면온도 모형은 기상·이력·태양위치 63특성 회귀다. 기본 12특성 회귀와 같은 관측쌍에서 비교한 MAE 차이를 보고했으며, 온도 오차 개선을 실제 Ice 판정 개선으로 대신 주장하지 않았다. 두 고정 결빙 판정법은 관측 대조 후 현재 기본법을 정리했다. 이 기본법 선택 자체를 전혀 보지 않은 독립 시험으로 해석하지 않으며, 보호 관측값으로 새 가중치나 문턱을 학습하지 않았다.

구간 기준은 14열 전체 입력 시계열을 비교해 같은 정보를 한 번 집계한다. 후보 조합 136개·235만 행에서 90개 중복 배열을 확인했고, 서로 다른 실제 입력 22개·24개를 겨울별 분위수의 단위로 사용했다. 기준 조합과 75개 민감도, 지형 원본·재현 코드를 함께 제시한다.

## 검증과 표현

모형·학습 자료·필수 예측 해시, 예제 및 지정 지점 기상 추론, 회귀·조건 집계, 실제 Jupyter 실행, CSV·공간 파일, 화면과 영상, PDF 렌더링을 확인했다. 실제 수치와 실행 결과를 본문 근거로 사용했다. 세 지정 지점의 기온·습도·풍속 결측은 NA로 남겼다.

공개 Anthropic Frontend Design, Scientific Agent Skills의 Scientific Critical Thinking·Scientific Visualization, Codex PDF 스킬의 절차를 참고했다. 비교 기준과 분모, 연관성과 인과효과, 독립 표본과 반복 입력의 구분, 실제 크기에서의 도표 검수를 적용했다.

- [Anthropic Frontend Design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)
- Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). [Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://doi.org/10.48550/arXiv.2609.00065)
- [Scientific Agent Skills 공개 라이브러리](https://github.com/K-Dense-AI/scientific-agent-skills)

공개 스킬 사용 자체를 성능이나 입상 가능성이 검증됐다는 근거로 취급하지 않았다. 물리적 해석과 자료 이용조건은 원천 문헌·라이선스를 따른다.
''','utf8')
source=(ROOT/'scripts/record_information_demo_20261106.py').read_text('utf8')
source=source.replace("'local_review/demo_inference_information.csv'","'local_review/demo_inference_team.csv'").replace("W/'information_demo_recording'","W/'team_demo_recording'").replace("W/'demo_build_information.json'","W/'demo_build_team.json'")
source=source.replace('<nav class="topnav">','<nav class="topnav"><a class="team-brand" href="../index.html">로드투인사이트</a>')
p=ROOT/'scripts/record_team_demo_20261106.py';assert not p.exists();p.write_text(source,'utf8')
old=B/'demo/model_demo.webm';saved=O/'model_demo_before_team_name.webm'
assert old.resolve().is_relative_to(W.resolve()) and saved.resolve().is_relative_to(W.resolve()) and not saved.exists();old.replace(saved)
print('로드투인사이트 팀명·문서 표기와 최종 데모 준비 완료')
