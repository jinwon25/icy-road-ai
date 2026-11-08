"""현 모형의 검증과 명시적F1선택·실제 구간 탐색을 22쪽 보고서에 통합한다."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1];P=ROOT/'outputs/private'


def main():
    target=ROOT/'docs/delivery/ANALYSIS_REPORT_V11_20261101.md'
    if target.exists():raise FileExistsError('Preserve manuscript')
    read=lambda p:json.loads(p.read_text(encoding='utf8'))
    physical=read(P/'weather_thermodynamics_20261101_v1/summary.json')
    cat=read(P/'weather_catboost_20261101_v1/summary.json')
    assert not physical['accepted_candidates'] and not cat['accepted_candidates']
    pages=(ROOT/'docs/delivery/ANALYSIS_REPORT_V10_20261101.md').read_text(encoding='utf8').split('<!-- page -->')
    assert len(pages)==19
    pages[0]=pages[0].replace('### 연구 질문과 핵심 결과','### 연구 질문과 핵심 결과')
    pages[0]=pages[0].replace('### 보고서 읽기','### 보고서 읽기')
    pages[0]+='\n현재 습도 모형의 추가 교체는 물리 입력·다른 나무 구조의 두 검증에서 지지되지 않았다. F1 우선의 기온 기준선 실행 후보와 두 겨울 구간 기상 탐색 화면을 함께 제공하여, 선택의 손해와 입력 품질도 검토하도록 했다.\n'
    physical_page='''## 4-4. 물리 관계와 다른 나무 구조의 추가 검증

기온·이슬점·습도 관계를 활용한 후처리 연구[14,15]를 참고하여 물·얼음 포화 수증기압, 포화 부족량, 서리점 등 18개와 수증기압·부족량의 과거 통계 24개를 추가했다. 기존 안정화 82개와 합쳐 124특성이다. 공식 IFS 수식[16]을 사용했지만, 논문의 공동 제약 신경망을 재현한 것은 아니다. 도로의 실측 습도나 노면온도를 입력하지 않았다.

직접 잔차와 0.5-99.5% 범위의 logit 잔차를 같은 HGB 설정으로 24회 적합했다. logit의 가중치는 물리 단위 L1의 국소 근사이며 정확한 동일 손실이 아니다. 별도로 82특성 그대로 CatBoost MAE 600회·깊이 6의 12모형과 기존 HGB의 고정 1:1 평균을 비교했다. 외부 모델·학습 자료는 반입하지 않았고 연도·지점 ID를 특성으로 넣지 않았다.

![그림 4. 기존 v10 대비 추가 후보의 MAE. 두 제외 검증의 모든 기준을 통과한 후보는 없었다.](../images/weather_followup_20261101.png)

| 모형 | 지역 제외 MAE | 지역·겨울 제외 MAE | 판정 |
| --- | --- | --- | --- |
| 현재 v10 | 5.686973 | 5.834129 | 유지 |
| 물리 입력·직접 잔차 | 5.658130 | 5.859290 | 겨울 전이 실패 |
| 물리 입력·logit | 5.764839 | 5.792880 | 겨울·개선폭 등 실패 |
| CatBoost | 6.247698 | 6.019081 | 악화 |
| HGB·CatBoost 1:1 | 5.792669 | 5.798354 | 양 겨울·개선폭 등 실패 |

직접 물리 입력의 지역 제외 개선은 약 0.51%였지만 지역·겨울 동시 제외에서는 악화했다. 평균 MAE 2%·양 겨울·지역 악화 제한·저온·날짜 블록 기준을 사후 완화하지 않았다. 물리 입력 33,370,890값·전 모형 추론·대표 4재학습, CatBoost 전량 추론·대표 2재학습과 지표를 별도 검산했다. 같은 개발 지역의 반복 비교이며 독립 성적이 아니다.
'''
    profile_page='''## 4-5. F1 우선 검토와 기존 결빙 판정의 선택 목적

기존 v2의 정밀도·겨울·사건 보존 기준은 연구자가 정한 보수적 채택 조건이며 공식 배점과 같지 않다. F1을 우선하여 검토할 수 있도록 이미 알려진 ASOS 기온 0°C 기준선을 별도 실행 프로필로 만들었다. 새로운 학습 성능이나 독립 점수 개선으로 주장하지 않는다. 기존 v2도 동일하게 실행·비교할 수 있다.

![그림 5. 기온 기준선의 통합 F1이 높아도 둘째 겨울에서는 낮아진다. 같은 개발 9곳의 두 겨울이다.](../images/competition_profiles_20261101.png)

| 같은 입력 가용 범위의 비교 | 기존 v2 | 기온 0°C |
| --- | --- | --- |
| 통합 일별 지점 F1 | 0.026554 | 0.036601 |
| 정밀도 / 재현율 | 0.040055 / 0.739628 | 0.033386 / 0.966799 |
| 2024/25 F1 | 0.030187 | 0.071179 |
| 2025/26 F1 | 0.009466 | 0.001444 |
| 386개 관측 사건 중 탐지 | 178개 | 330개 |

기온 기준선은 더 많은 결빙을 포착했지만 정밀도와 둘째 겨울 F1은 낮았다. 점수가 높은 단일 숫자로 현장 적합성이나 보호 지점 성능을 보장하지 않는다. 미정의 날짜·희소 양성·특정 지점 집중 때문에 점수와 날짜 분모·사건을 함께 본다. 사후 최고 임계값을 골라 새 후보로 바꾸지 않았다.

`scripts/predict_competition_profile.py`에서 `--icing-profile preserved_v2` 또는 `score_priority_asos_zero`를 명시한다. 온도 v3·현재 기상 추정은 바꾸지 않으며 기존 v2 판정·근거·기준 온도도 열로 보존한다. 보호 103,680행에서 온도·행키·입력 부족 18행을 정확히 보존했고 실제 CLI 두 경로의 144행을 검증했다. 보호 정답은 읽지 않았다.

새 기상과 v3 온도로 서리 조건을 더한 고정 합집합 규칙은 추가 정탐 0·오경보 121행, F1 0.036549로 실패했다. 예측을 먼저 봉인한 후 기존 개발 정답으로 평가하고 별도 수식·2,486,216재추론 값·324지표를 검산했다. 실패한 서리 규칙이나 기상 개선을 결빙 개선으로 대신하지 않는다.
'''
    explorer_page='''## 4-6. 두 겨울의 구간 기상과 입력 품질을 직접 검토

같은 변수의 두 겨울을 같은 색 범위로 표시하고, 선택한 500m 보고 구간의 240일 시계열을 겹쳐 비교하는 오프라인 화면을 만들었다. 노선·방향·새 기상 출처·습도 특성 범위 이탈로 좁힐 수 있다. 기온·상대습도·1분 풍속뿐 아니라 과거 문맥 부족과 범위 이탈을 지도에서 확인한다.

![그림 6. 실제 오프라인 기상 탐색 화면의 지도·선택 구간·두 겨울 시계열. 화면에서 240일 CSV와 전체 자료로 이어진다.](../images/weather_explorer_20261101.png)

| 확인 | 실제 검증 |
| --- | --- |
| 원본 수치 | 843구간·일별 202,320행과 겨울별 1,686행, 1,632,048값 대조 |
| 화면·다운로드 | 실제 브라우저 126필터, 클릭·확대·날짜 확인·CSV 240행·상대 경로 3개 |
| 로컬·모바일 | 외부 요청 0·JavaScript 오류 0, 390px 가로 넘침 없음·화면 검토 |

모델자료의 `research/latest/weather_explorer_20261101_v2/index.html`을 현재 Chrome·Edge에서 연다. 설치·인증·외부 지도 타일이 필요하지 않다. 단일 HTML에 추정값을 포함하며 전체 CSV·GIS는 함께 둔 상대 경로에서 연다. 표시용 일별 값은 소수 여섯 자리이며 전체 원본은 별도 제공한다.

ASOS 172 출처 50구간과 입력 범위 이탈은 정확도·오차 구간이 아니다. 보고 구간이 가까운 기상을 공유한다는 사실도 그대로 유지한다. 이 화면은 구간 선택과 자료 검토를 돕는 도구이며 결빙확률·공식 위험등급이나 자동 제설 판단을 검증한 결과가 아니다.
'''
    pages[15]=pages[15].replace('19쪽','22쪽').replace('analysis_report_v10.pdf','analysis_report_v11.pdf').replace('submission_review_v10.ipynb','submission_review_v11.ipynb')
    pages[17]+='''

### 추가 물리·알고리즘 참고

[14] Zanetta et al. (2023). Physics-constrained deep learning postprocessing of temperature and humidity. AIES, e220089. 원 수식과 공개 구현의 station embedding·5목표 조건을 대조했다. 저자 코드·스위스 관측·사전학습 모형은 반입하지 않았다. https://arxiv.org/html/2212.04487v2

[15] Casellas et al. (2026). Joint Postprocessing of Air and Dew Point Temperature Ensemble Forecasts With Machine Learning. Meteorological Applications, e70237. 공동 확률분포의 연구 동기를 참고했으며 본 deterministic 공간 복원의 성능으로 사용하지 않았다. https://doi.org/10.1002/met.70237

[16] ECMWF earthkit-meteo. saturation_vapour_pressure, IFS 물·얼음 단일 상 수식·단위. CatBoost 공식 문서의 MAE·수치형 결측·대칭 나무 구조를 대조했다. 상세 주소·고정 커밋·BSD-3-Clause 조건은 후속 연구 문서에 있다.
'''
    pages[18]+='\n추가 검토는 `weather_thermodynamics_20261101_v1`, `weather_catboost_20261101_v1`, `frost_icing_20261101_v1`의 계획·전량 추론·재학습·독립 감사로 추적한다. `competition_profile_review_20261101_v1`은 선택 목적과 실제 CLI·보호 예측의 보존, `weather_explorer_validation_20261101_v4`는 실제 화면·숫자·CSV의 근거다. Codex의 실행을 참가자의 수동 검토로 대신 기록하지 않는다.\n'
    final=pages[:8]+[physical_page,profile_page,explorer_page]+pages[8:]
    assert len(final)==22
    text='\n\n<!-- page -->\n\n'.join(p.strip() for p in final)+'\n'
    text=text.replace('analysis_report_v10.pdf','analysis_report_v11.pdf').replace('submission_review_v10.ipynb','submission_review_v11.ipynb')
    text=text.translate(str.maketrans({'–':'-','—':'-','−':'-','‑':'-'}))
    target.write_text(text,encoding='utf8');print('V11 MANUSCRIPT',len(final),flush=True)


if __name__=='__main__':main()
