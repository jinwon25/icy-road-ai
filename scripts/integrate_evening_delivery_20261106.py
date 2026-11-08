"""최종 화면의 탐색 경로와 문서에 실제 계측 계획을 연결한다."""
from pathlib import Path
import re,shutil,subprocess,sys,json
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/private/evening_refinement_20261106'
B=W/'icy_road_model';D=W/'icy_road_documents'

def add_nav(path,href):
    s=path.read_text('utf8')
    assert 'href="'+href+'"' not in s[:s.index('</nav>')]
    s,n=re.subn(r'(</nav>)',f'<a href="{href}">현장 확인</a>\\1',s,count=1)
    assert n==1
    path.write_text(s,'utf8')

def main():
    for rel,href in [('index.html','results/field/index.html'),('maps/sections.html','../results/field/index.html'),
                     ('assets/inspection_template.txt','../results/field/index.html')]:add_nav(B/rel,href)
    subprocess.run([sys.executable,'-X','utf8',str(B/'code/build_section_explorer.py'),'--output',str(B/'local_review/sections_final.html')],check=True)
    assert (B/'maps/sections.html').read_bytes()==(B/'local_review/sections_final.html').read_bytes()
    for filename in ['README.md','AI_USAGE.md']:
        path=B/filename;s=path.read_text('utf8')
        if filename=='README.md':
            s=s.replace('## 환경과 추론','''## 현장 확인 계획

[두 범위의 확인 계획](results/field/index.html)은 선정 범위의 대표 중점 A와 같은 기상 입력을 공유하는 인접 비선정 구간 B를 나란히 보여 준다. 두 비교 후보는 약 500m 거리이며 선형 변화는 기준 조합에 미치지 않는다. 같은 기상 입력으로는 도로의 차이를 더 구분하기 어려워 노면수분·염분·제빙 이력을 함께 기록하도록 구성했다.

[2쪽 인쇄용 계획서](results/field/field_measurement_plan.pdf), [비교 후보 원표](results/field/comparison_candidates.csv), [대표 중점 GIS](results/field/measurement_plan.gpkg)를 제공한다. 화면에서는 미측정 값을 비워 둔 채 기록 파일을 저장·불러오거나 CSV로 내보낼 수 있다. 실제 현장 확인과 측정은 수행하지 않았다.

계획을 다시 생성하려면 지리 라이브러리 설치 후 새 출력 폴더를 지정한다. 인쇄용 PDF는 HTML의 인쇄 기능으로 만든다.

    python code/build_field_plan.py --output local_review/field_plan

## 환경과 추론''')
        else:
            s+='''
## 계측 계획과 화면 구성

선정 범위와 같은 기상 입력을 공유하는 인접 비선정 구간을 같은 시각에 비교하는 계측 계획을 작성했다. 포함 중심선·기상 입력 식별자·지형 원표만 사용했으며 보호 지점의 정답으로 위치를 선택하지 않았다. 실제 계측을 수행한 것처럼 채워 넣지 않고 빈 기록 양식을 제공했다.

현장 수분·제빙 기록의 필요성은 [RoadSurf](https://gmd.copernicus.org/articles/17/4837/2024/gmd-17-4837-2024.html), 수집 목적과 자료 해상도를 함께 설명하는 방식은 [FHWA](https://ops.fhwa.dot.gov/publications/fhwahop20051/index.htm)를 참고했다. 노선 요약에서 지도 상세와 확인 행동으로 이어지는 정보 순서는 [Vaisala 사용자 안내](https://guide.wxhorizon.vaisala.com/en-US/using_the_dashboard.html)를 참고했다. 서비스 화면·상표·수치 예시는 복제하지 않았다.
'''
        path.write_text(s,'utf8')
    shutil.copyfile(B/'AI_USAGE.md',D/'AI_USAGE.md')
    shutil.copyfile(B/'results/field/field_measurement_plan.pdf',D/'report/field_measurement_plan.pdf')
    for name in ['comparison_candidates.csv','measurement_protocol.csv']:
        shutil.copyfile(B/'results/field'/name,D/'data'/name)
    path=D/'README.md';s=path.read_text('utf8')
    s+='''
[2쪽 현장 확인 계획서](report/field_measurement_plan.pdf)는 선정 범위와 약 500m 떨어진 인접 비교 후보를 지도·좌표·선형 변화와 함께 보여 준다. [비교 후보 CSV](data/comparison_candidates.csv)와 [계측 항목](data/measurement_protocol.csv)을 함께 제공한다. 두 지점의 같은 기상 입력을 전제로, 실제 노면수분·염분·제빙 이력의 차이를 확인할 계획이다. 실제 현장 계측은 수행 전이며 기록 표는 비워 뒀다.
'''
    path.write_text(s,'utf8')
    summary=json.loads((B/'summary.json').read_text('utf8'));summary['status']='verified_offline_analysis'
    summary['current_field_plan']='results/field/index.html'
    (B/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
    print('계측 계획·실행 안내·문서자료를 연결했습니다.',flush=True)

if __name__=='__main__':main()
