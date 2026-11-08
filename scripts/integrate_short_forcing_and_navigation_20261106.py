"""검토 가능한 실패 근거와 현재 열람 안내를 제출 작업본에 연결한다."""
from pathlib import Path
import json,sys,shutil
from datetime import datetime,timezone,timedelta
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
P=ROOT/'outputs/private';W=P/'late_research_design_20261106';B=W/'icy_road_model';D=W/'icy_road_documents';E=P/'short_forcing_icing_20261106'
def put(p,v):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
def read(p):return json.loads(p.read_text('utf8'))
def main():
    result=read(E/'summary.json');audit=read(E/'audit.json');assert not result['promote']
    folder=B/'results/evaluation/short_forcing_review';folder.mkdir()
    f=pd.read_parquet(E/'predictions.parquet',columns=['station','time','winter','group','ice','physical','asos_zero','candidate'])
    assert len(set(f.station))==9 and not set(f.station)&{'12410','33411','23402','33402','33406','12213','23411'}
    f.to_parquet(folder/'predictions.parquet',index=False,compression='zstd')
    rows=[]
    for name in ['physical','asos_zero','candidate']:
        r=result['reports'][name]
        for scope,report in [('all',r['1']),('strict144',r['144']),*r['winters'].items(),*r['regions'].items()]:
            rows.append(dict(method=name,scope=scope,**{k:report[k] for k in ['precision','recall','f1','tp','fp','fn']}))
    pd.DataFrame(rows).to_csv(folder/'comparison.csv',index=False)
    feasible=sum(int(pd.read_csv(p).track.eq('precision').sum()) for p in E.glob('*__selection.csv'))
    assert feasible==0
    compact=dict(status='short_forcing_candidate_not_promoted',source='https://arxiv.org/abs/2609.33528',source_type='preprint',
        scope='ASOS air and ground temperature proxies; not the paper observed-pavement input or future-onset target',
        decay_minutes=[10,30,120],new_model_fits=20,threshold_searches=16,outer_regions=4,inner_pair_exclusions=6,
        common_valid_pairs=309928,guarded_precision_feasible_candidates=feasible,
        metrics={n:{k:r['1'][k] for k in ['precision','recall','f1']} for n,r in result['reports'].items()},
        decisions=result['decisions'],promotion_gates=result['promotion_gates'],promote=False,
        formula_audit={'status':audit['status'],'constant_cold_closed_form_max_error':audit['constant_cold_closed_form_max_error'],
            'missing_time_gap_resets':True,'station_isolation_exact':True,'model_reload_exact':20,
            'strict_past_perturbation_passed':read(E/'feature_checks.json')['strict_past_perturbation_passed']},
        saved_predictions_sha256=sha(folder/'predictions.parquet'),saved_comparison_sha256=sha(folder/'comparison.csv'),
        protected_outcomes_used=False,external_four_outcomes_used=False,new_independent_assessment=False,production_model_changed=False,
        reproduction_scope='code/analyze_short_forcing_review.py recomputes metrics from included fixed out-of-fold predictions; it does not refit the experimental classifiers.')
    put(B/'technical/short_forcing_review.json',compact);put(D/'data/short_forcing_review.json',compact)
    shutil.copy2(folder/'comparison.csv',D/'data/short_forcing_comparison.csv')
    p=B/'README.md';s=p.read_text('utf8');needle='## 완성물 확인\n\n';assert s.count(needle)==1
    s=s.replace(needle,needle+'[결과 요약 화면](start.html)에서 분석 범위와 온도 성과·결빙의 한계·계측 후보를 먼저 확인할 수 있다. 각 결과에서 원표와 보고서 해당 쪽으로 이동한다. 보고서는 14개 책갈피와 첫 쪽의 질문별 이동 링크를 제공한다.\n\n')
    s=s.replace('    python code/analyze_inventory_agreement.py --output local_review/inventory_agreement','    python code/analyze_inventory_agreement.py --output local_review/inventory_agreement\n    python code/analyze_short_forcing_review.py --output local_review/short_forcing_review')
    p.write_text(s,'utf8')
    addition='''
## 짧은 기상 이력과 열람 구성

[Yi·Seo의 사전 공개 연구](https://arxiv.org/abs/2609.33528)에서 감쇠 누적이라는 가설을 참고해 ASOS 기온·지면온도 대리 입력의 10·30·120분 이력을 검토했다. 해당 연구의 실제 노면온도와 미래 결빙 시작 예측을 재현한 것은 아니다. 두 가중 방식과 10개 지역 제외 조합으로 20개 모형을 학습하고 16개 내부 문턱 선택을 확인했다. 지역 제외 F1 0.0038은 고정 물리 기준 0.0294보다 낮아 채택하지 않았다. 감쇠식의 해석해, 결측 시간의 초기화, 지점 분리, 미래 입력 교란과 20개 저장 모형의 동일 점수 재현을 확인했다. [검토 근거](technical/short_forcing_review.json)를 제공한다. 지정 평가 지점과 외부 보류 지점의 정답으로 이 후보를 선택하지 않았다.

결과 요약에서 비교 근거와 원표로 이동하는 순서, 도표의 메시지·분모·기간을 가까이 두는 구성은 [영국 정부 분석 지침](https://analysisfunction.civilservice.gov.uk/policy-store/data-visualisation-charts/)과 [교육부 차트 안내](https://design.education.gov.uk/design-system/patterns/charts)를 참고했다. 실제 전북 도로와 계산값으로 구성했으며, 보고서의 질문별 이동과 책갈피, 영상 미리보기·장면 이동·문자 설명, 키보드 표 이동을 추가했다. 접근성 전체 준수를 인증한 결과는 아니다.
'''
    p=B/'AI_USAGE.md';s=p.read_text('utf8');assert '## 짧은 기상 이력과 열람 구성' not in s;s+='\n'+addition;p.write_text(s,'utf8')
    (D/'AI_USAGE.md').write_text(s.replace('results/evaluation/fixed_temperature_rule_review/comparison.csv','data/fixed_temperature_rule_comparison.csv').replace('technical/threshold_selection_review.json','data/threshold_selection_review.json').replace('technical/short_forcing_review.json','data/short_forcing_review.json'),'utf8')
    p=D/'README.md';s=p.read_text('utf8');s+='\n보고서 첫 쪽의 질문별 링크와 14개 책갈피에서 필요한 부분으로 이동할 수 있다. 짧은 감쇠 이력 후보의 미채택 근거는 [추가 검토 표](data/short_forcing_comparison.csv)와 [범위·검산](data/short_forcing_review.json)에 정리했다. 모델자료의 start.html은 온도 비교·결빙 한계·목록 대조·실행 재현을 연결한다.\n';p.write_text(s,'utf8')
    official=read(B/'technical/official_evening_access_review.json')
    official.update(at_kst=datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M'),
        task_main_page_status='public_title_and_provided_data_listing_rechecked',task_main_page_title='기상과 도로환경 융합자료를 활용한 AI기반의 전북도 고속도로 결빙위험도 분석 제시',
        latest_notice_titles_unchanged=True,latest_general_question_titles_unchanged=True,
        detailed_refresh_attempts=[{'id':i,'status':'web_tool_inaccessible'} for i in [693,716,807,811]])
    put(B/'technical/official_evening_access_review.json',official)
    put(W/'integration.json',dict(status='integrated',research_promoted=False,model_or_prediction_values_changed=False,new_result_entry='start.html'))
    print('Integrated research limits, reproducible comparison data and result-reading guidance',flush=True)
if __name__=='__main__':main()
