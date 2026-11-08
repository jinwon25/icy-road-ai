"""완료한 결빙 정밀도 실험을 사용자 검토용 표·그림·오프라인 화면으로 정리한다."""
from pathlib import Path
from datetime import datetime,timezone
import json,html
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'outputs/private'
OUT=P/'icing_precision_review_20261106'

def read(p):return json.loads(p.read_text('utf8'))

def main():
    sources={
        '기상 이력 학습':P/'icing_precision_comparison_20261106/summary.json',
        '노면상태 구분 학습':P/'icing_multistate_comparison_20261106/summary.json',
        '가까운 기상·지형 융합':P/'icing_local_context_20261106/summary.json',
        '적설 증가 이력':P/'icing_snow_age_20261106_checked/summary.json'}
    all_results={k:read(v) for k,v in sources.items()}
    if any(v['promote'] for v in all_results.values()):
        raise RuntimeError('A candidate passed promotion: integrate and verify before writing a keep-current decision')
    audit=read(OUT/'independent_audit.json')
    assert audit['status']=='passed'
    diagnosis=read(P/'icing_precision_diagnosis_20261106/summary.json')
    identities=read(P/'icing_input_identifiability_20261106/summary.json')['results']
    s=all_results['기상 이력 학습']['reports']
    rows=[]
    def row(label,report,status):
        m=report['1'];e=report['events']
        rows.append(dict(방법=label,정밀도=m['precision'],재현율=m['recall'],F1=m['f1'],
                         오경보=m['fp'],미탐=m['fn'],추가누락사건=e['lost_events'],판단=status))
    row('현재 제출 모델',s['physical_both'],'유지')
    row('기온 0°C 기준선',s['asos_zero'],'비교 기준')
    row('기상 이력 학습',s['f1_track'],'교체 기준 미충족')
    row('노면상태 구분 학습',all_results['노면상태 구분 학습']['reports']['f1_track'],'교체 기준 미충족')
    row('가까운 기상·지형 융합',all_results['가까운 기상·지형 융합']['reports']['f1_track'],'교체 기준 미충족')
    row('적설 증가 6시간',all_results['적설 증가 이력']['reports']['snow_growth_6h'],'미탐 증가')
    row('적설 증가 24시간',all_results['적설 증가 이력']['reports']['snow_growth_24h'],'미탐 증가')
    table=pd.DataFrame(rows)
    table.to_csv(OUT/'comparison.csv',index=False,encoding='utf-8-sig')
    font=font_manager.FontProperties(fname='C:/Windows/Fonts/malgun.ttf').get_name()
    plt.rcParams.update({'font.family':font,'axes.unicode_minus':False,'font.size':10,
        'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,
        'axes.edgecolor':'#c8cdc8','text.color':'#182d35','axes.labelcolor':'#182d35',
        'xtick.color':'#50656a','ytick.color':'#182d35','figure.facecolor':'#faf9f5','axes.facecolor':'#faf9f5'})
    # 오경보의 관측 노면 상태: 상호 배타적인 유효 원코드 집계.
    states=pd.read_csv(P/'icing_precision_diagnosis_20261106/false_alarm_surface_states.csv')
    groups=[('건조 상태 (01·10)',[1,10]),('습윤 상태 (02·11)',[2,11]),
            ('적설 상태 (03)',[3]),('기타 유효 상태 (12·13·14·15)',[12,13,14,15])]
    values=[int(states.loc[states.state.isin(ids),'fp'].sum()) for _,ids in groups]
    assert sum(values)==diagnosis['fp']
    fig,ax=plt.subplots(figsize=(10.5,3.4))
    y=np.arange(len(groups));ax.barh(y,values,color=['#1c5a67','#557f87','#a7bab8','#c19a67'],height=.55)
    ax.set_yticks(y,[label for label,_ in groups]);ax.invert_yaxis();ax.tick_params(axis='y',length=0,pad=12)
    ax.set_xlim(0,max(values)*1.28);ax.set_xlabel('오경보 관측 수 · 10분 단위')
    for yy,v in zip(y,values):ax.text(v+max(values)*.025,yy,f'{v:,}건  ·  {v/sum(values)*100:.1f}%',va='center')
    ax.grid(axis='x',alpha=.16);ax.set_axisbelow(True);fig.tight_layout(pad=1.5)
    fig.savefig(OUT/'false_alarm_states.png',dpi=180);plt.close(fig)
    # 공식 집계 방식의 Precision/Recall: 각 날짜·지점 평균, 행 합산 비율과 구분.
    labels=table.방법.tolist();yy=np.arange(len(table))
    fig,axes=plt.subplots(1,3,figsize=(12,4),sharey=True,gridspec_kw={'width_ratios':[1,1,1]})
    for ax,column,title in zip(axes,['정밀도','재현율','F1'],['정밀도 (%)','재현율 (%)','F1']):
        v=table[column].to_numpy(float)*(100 if column!='F1' else 1)
        ax.barh(yy,v,color=['#1c5a67']+['#b8c8c5']*(len(v)-1),height=.54)
        ax.set_title(title,loc='left',fontsize=12,pad=14)
        ax.set_yticks(yy,labels);ax.tick_params(axis='y',length=0,pad=10)
        ax.set_xlim(0,max(v)*1.30 if max(v) else 1);ax.grid(axis='x',alpha=.16);ax.set_axisbelow(True)
        for y0,x0 in zip(yy,v):ax.text(x0+ax.get_xlim()[1]*.025,y0,f'{x0:.2f}' if column!='F1' else f'{x0:.4f}',va='center',fontsize=9)
    axes[0].invert_yaxis();fig.tight_layout(pad=1.4)
    fig.savefig(OUT/'precision_recall_f1.png',dpi=180);plt.close(fig)
    fp=diagnosis['fp'];cold=diagnosis['false_alarm_surface_at_or_below_zero']/fp*100
    snow=sum(r['fp'] for r in diagnosis['by_water_source'] if '적설' in r['water_source'])/fp*100
    body=[]
    for r in rows:
        values=[html.escape(r['방법']),f"{r['정밀도']*100:.2f}%",f"{r['재현율']*100:.2f}%",f"{r['F1']:.4f}",
                f"{r['오경보']:,}",f"{r['추가누락사건']:,}",html.escape(r['판단'])]
        body.append('<tr>'+''.join('<td>'+v+'</td>' for v in values)+'</tr>')
    content=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>결빙 경보 검증</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#faf9f5;color:#182d35;font:16px/1.8 "Malgun Gothic",sans-serif}}
main{{max-width:1160px;margin:auto;padding:64px 36px 70px}}.eyebrow{{font-size:13px;color:#557078;letter-spacing:.12em}}
h1{{word-break:keep-all;font-size:44px;line-height:1.25;letter-spacing:-.055em;margin:13px 0 24px}}h2{{font-size:25px;letter-spacing:-.035em;margin:42px 0 14px}}
p{{max-width:870px;margin:10px 0 18px}}.lead{{font-size:20px;line-height:1.8;max-width:940px}}
.rule{{border-top:2px solid #1c5a67;margin:34px 0}}.note{{font-size:14px;color:#50656a;line-height:1.75}}
a.figure-link{{display:block;cursor:zoom-in}}.mobile-hint{{display:none;font-size:13px;color:#50656a}}img{{display:block;width:100%;height:auto;margin:16px 0 8px}}.table-wrap{{overflow-x:auto;border-top:2px solid #1c5a67}}
table{{width:100%;border-collapse:collapse;font-size:14px;white-space:nowrap}}th,td{{padding:13px 10px;border-bottom:1px solid #d7ddda;text-align:right}}
th{{font-weight:400;color:#50656a}}td:first-child,th:first-child{{text-align:left}}tr:first-child td{{font-weight:bold;background:#e9efec}}
td:last-child,th:last-child{{text-align:left}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:36px}}
.two p{{font-size:15px}}a{{color:#1c5a67;text-underline-offset:4px}}details{{border-top:1px solid #cdd6d1;margin-top:32px;padding-top:18px}}
summary{{cursor:pointer;font-size:15px}}footer{{margin-top:44px;padding-top:22px;border-top:1px solid #cdd6d1;font-size:13px;color:#50656a}}
@media(max-width:650px){{.mobile-hint{{display:block}}main{{padding:32px 20px 45px}}h1{{font-size:33px}}h2{{font-size:22px}}.lead{{font-size:18px}}.two{{grid-template-columns:1fr;gap:0}}}}
</style><main>
<div class="eyebrow">ICY ROAD · 결빙 경보의 정확성</div>
<h1>결빙 오경보의 원인과<br>추가 모델의 검증 결과</h1>
<p class="lead">추가 입력과 판정 방법을 지역별로 분리해 검증했습니다. 정밀도·재현율·F1과 기존에 탐지하던 결빙 사건을 함께 비교한 결과, 제출 모델을 교체할 만큼 안정적인 개선을 확인하지 못했습니다. 현재 검증된 제출 모델을 유지합니다.</p>
<p class="mobile-hint">표는 좌우로 이동하고, 그림은 눌러 확대할 수 있습니다.</p><div class="rule"></div>
<h2>어디에서 오경보가 생겼는가</h2>
<p>기존 개발 자료의 오경보 {fp:,}건 중 {cold:.1f}%는 실제 노면온도도 영하였고, {snow:.1f}%는 주변 ASOS의 적설을 수분 근거로 사용한 경보였습니다. 영하의 도로와 주변 지면의 적설만으로 현재 도로의 Ice 상태를 확정하기 어렵습니다.</p>
<a class="figure-link" href="false_alarm_states.png" aria-label="오경보 상태 그림 크게 보기"><img src="false_alarm_states.png" alt="오경보의 실제 노면 상태별 관측 수"></a>
<p class="note">그림은 실제 유효 노면상태 원코드의 분포입니다. 영하 비율과 적설 근거 비율은 서로 겹치는 조건입니다. 이 진단에서 관측 노면온도·상태는 원인 분석에만 사용했습니다.</p>
<h2>정밀도 상승과 미탐을 함께 비교</h2>
<div class="table-wrap"><table><thead><tr><th>방법</th><th>정밀도</th><th>재현율</th><th>F1</th><th>오경보 관측</th><th>추가 누락 사건</th><th>판단</th></tr></thead>
<tbody>{''.join(body)}</tbody></table></div>
<p class="note">정밀도·재현율·F1은 공식 Q&A에 따른 날짜 → 지점 평균입니다. 오경보는 평균 지표에서 제외된 무결빙 지점도 포함한 전체 유효 관측쌍의 합계입니다. ‘추가 누락 사건’은 현재 모델이 탐지하던 연속 결빙 사건을 새 방법이 놓친 수입니다. 다른 사건을 추가로 탐지한 수와 상쇄하지 않았습니다.</p>
<a class="figure-link" href="precision_recall_f1.png" aria-label="성능 비교 그림 크게 보기"><img src="precision_recall_f1.png" alt="현재 모델과 추가 입력·적설 정책의 정밀도, 재현율 및 F1 비교"></a>
<div class="two"><section><h2>적설 경보를 좁혔을 때</h2><p>최근 6시간 안에 적설 증가가 없던 경보를 줄이면 오경보 {all_results['적설 증가 이력']['reports']['baseline']['1']['fp']-all_results['적설 증가 이력']['reports']['snow_growth_6h']['1']['fp']:,}건을 덜 냅니다. 그러나 기존에 잡던 결빙 사건 20개를 놓칩니다. 정밀도 수치만 보고 채택하지 않은 이유입니다.</p></section>
<section><h2>기상 이력을 더했을 때</h2><p>ASOS 53개 입력에서는 결빙 관측 {identities['process']['observed_ice']:,}건 모두가 다른 도로의 비결빙 관측과 동일한 기상 표현을 공유했습니다. 이는 해당 입력과 관측 표본에서 확인한 구분의 한계이며, 모든 결빙 모델의 성능 한계나 관측 오류를 뜻하지 않습니다.</p></section></div>
<h2>다음 개선에 필요한 자료</h2>
<p>도로 위 수분·얼음의 직접 계측, 위치와 시각이 붙은 제설·제빙 이력, 설치 지점의 교량·포장·차폐 조건이 우선입니다. 같은 기상권의 도로가 왜 다른 상태가 되었는지 설명할 정보가 필요합니다. 제공 교량 자료는 외부 평가 지점의 범위를 덮지 않아 학습 지점에 억지로 연결하지 않았습니다.</p>
<details><summary>검증 조건과 재현 근거</summary>
<p class="note">허용 23지점·두 겨울로 학습하고 개발 9지점을 4개 지역으로 묶었습니다. 외부 지역과 내부 선택 지역을 모두 제외해 학습했으며, 문턱·방법은 내부 지역에서만 선택했습니다. 기간 내 실제 Ice가 없는 33205는 평균 지표에서 제외했습니다. 주 집계는 최소 1개 유효 관측의 날짜이며, 완전한 144개 날짜도 별도로 검산했습니다.</p>
<p class="note">이 자료는 이미 반복 사용한 개발 지점의 추가 검증입니다. 보고서의 보호 지점 평가와 구별합니다. 보호 3지점과 기개봉 외부 4지점의 정답은 새 학습·선택에 사용하지 않았습니다. 노면상태 구분은 학습 정답의 구성만 바꾼 것으로, 추론 입력에 관측 노면상태를 넣지 않았습니다. 기상 캐시 가용 범위가 달라 제외한 216행은 기존 모델에도 같은 마스크를 적용했습니다. 관측 양성 지점의 제외 여부는 예측 가용성과 무관하게 정했습니다.</p>
<p class="note">독립 검산: {audit['new_model_fits']}개 새 적합의 학습 범위, 직렬화한 모델 재실행, 공식 집계의 별도 계산, 보호 평가 봉인과 두 제출 ZIP의 해시를 확인했습니다. 세부 수치는 <a href="comparison.csv">비교 CSV</a>와 <a href="independent_audit.json">검산 영수증</a>에 있습니다.</p>
<p class="note">과정 입력의 근거는 <a href="https://gmd.copernicus.org/articles/17/4837/2024/">RoadSurf의 수분·동결·해빙 구분</a>을 참고했습니다. RoadSurf를 구현하거나 얼음의 양을 물리적으로 재현한 모델은 아닙니다. 학습기는 <a href="https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html">scikit-learn HGB</a>입니다.</p></details>
<footer>제출 자료: <a href="../competition_submission/README.md">두 ZIP과 제출 안내</a> · <a href="../competition_submission/icy_road_model/index.html">분석 화면</a> · <a href="../competition_submission/icy_road_model/report/analysis_report.pdf">최종 분석 보고서</a><br>학습 모형과 예측값은 유지하고, 오경보 해석과 재현 자료를 제출 묶음에 보강했습니다. 실제 사이트 업로드는 수행하지 않았습니다.</footer>
</main></html>'''
    (OUT/'index.html').write_text(content,'utf8')
    result=dict(status='precision_review_built',at_utc=datetime.now(timezone.utc).isoformat(),
        production_model_changed=False,all_candidates_failed_promotion=True,submission_documents_updated=True,
        sources={k:v.relative_to(ROOT).as_posix() for k,v in sources.items()},rows=rows,
        diagnosis=dict(false_alarms=fp,actual_surface_at_or_below_zero_pct=cold,snow_evidence_pct=snow))
    (OUT/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print('BUILT',OUT/'index.html',flush=True)

if __name__=='__main__':main()
