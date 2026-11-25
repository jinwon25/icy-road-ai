# 변경 기준

대회 종료 후 이 저장소의 코드와 문서를 수정할 때 적용하는 기준입니다. 결과를 인용할 때는 검증 대상과 집계 단위를 함께 적습니다.

[프로젝트 소개](../README.md) · [문서 목록·용어 풀이](../docs/README.md)

README·About·결과 설명·커밋 메시지는 한국어로 작성한다. 모델명과 코드 식별자는 필요한 원문을 유지한다.

개발용 검증과 공식 보호 지점 평가, 노면온도 회귀와 결빙 분류, 정적 도로 구간과 위험도 지도를 구별한다. 구버전 데이터의 수치를 최종 성능으로 소개하지 않는다. AI 지원 내용과 참가자 확인이 필요한 내용을 `AI_USAGE.md`에 기록한다.

원본·파생 행·모델·예측·신청서·인증정보를 커밋하지 않는다. 공개 상태를 바꾸기 전에 [공유 범위](PUBLICATION.md)를 확인한다. 문서 이동 시 코드·설정·노트북 링크도 수정한다.

## 검증 방법

[루트 README](../README.md#프로젝트-실행)에 따라 개발 의존성과 CPU용 PyTorch를 설치한 뒤 CI와 같은 검사를 실행합니다.

```powershell
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python -m pytest -q tests
python scripts/check_repository.py
python scripts/check_markdown.py
```

Markdown은 띄어쓰기·수치·검증 범위를 먼저 확인하고 로컬 GFM으로 표·강조·코드·링크·앵커를 검증한다. 최신 상태와 과거 기록을 구분하고 원본 변수·명령·URL은 보존한다.

합성 자료 테스트는 공개 파일만으로 실행합니다. 대회 제공 데이터 폐기 후의 재현 범위는 [공유 범위](PUBLICATION.md)에 기록합니다.