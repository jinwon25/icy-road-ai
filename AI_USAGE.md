# AI 활용 내역

분석 설계 검토, 코드 작성과 수정, 실험 실행 및 결과 대조, 보고서와 데모 편집에 Codex를 활용했다. 지표와 지도 수치는 로컬 Python 프로그램으로 계산했으며 외부 생성형 AI 예측 API를 추론에 사용하지 않았다.

보고서는 관측·추정의 대조, 평가 분모와 한계, 도로 관리에서의 활용 범위를 중심으로 구성했다. 공개 [Frontend Design 스킬](https://github.com/anthropics/skills/tree/main/skills/frontend-design)의 시각적 위계와 사용자 관점 문구 원칙, PDF 렌더·검수 절차를 참고했다. 도로기상 방법과 해석에 사용한 학술·기관 자료는 보고서 참고문헌에 기재했다.

모형 학습·평가 범위, 입력 자료, 결측 처리와 지표 집계 방식은 코드와 보고서에 명시했다. 제공 자료는 승인된 대회 목적의 비공개 자료이며 공개·재배포 허용을 전제로 하지 않는다.

## 추가 검토와 미채택 이유

[Yi·Seo의 사전 공개 연구](https://arxiv.org/abs/2609.33528)의 감쇠 누적 가설을 참고해 ASOS와 가까운 AWS의 단기 기상 이력 후보를 각각 20회 학습했다. 두 후보의 지역 제외 F1은 0.0038·0.0039로 고정 물리 기준 0.0294보다 낮아 채택하지 않았다. 원 연구는 실제 노면온도를 쓰는 미래 결빙 시작 예측으로 입력·목표가 다르며 외부 연구의 성능을 우리 성능으로 인용하지 않았다. 보호 지점과 외부 보류 지점의 정답으로 이 후보를 선택하지 않았다.

공개 Anthropic Frontend Design·Webapp Testing과 Vercel Web Design Guidelines를 프로젝트 참고 사본으로 받아 원본 Git blob 해시를 대조했다. [영국 정부 분석 지침](https://analysisfunction.civilservice.gov.uk/policy-store/data-visualisation-charts/)과 [Dribbble의 공개 비교 화면](https://dribbble.com/shots/26240563--Clima-dashboard)을 참고해 비교 분모·기간을 도표에 붙이고 주제별 분석·영상 장면 이동·한글 줄바꿈·작은 화면을 검수했다. 일부 원본 이미지 직접 열람에는 연결 제한이 있었으며 디자인 이미지·상표·예시 수치는 복제하지 않았다. 공개 스킬 사용 자체를 성능이나 입상 가능성이 검증됐다는 근거로 취급하지 않았다.

보고서 수치 대조·PDF 렌더 검사·브라우저 조작과 자동 검증은 Codex가 수행했다. 사용자의 목표·방향 제시와 실제 참가자의 직접 검토를 구분한다. 상세한 방법·한계·출처는 [최종 보고서 원고](docs/delivery/FINAL_ANALYSIS_REPORT.md)를 따른다.
