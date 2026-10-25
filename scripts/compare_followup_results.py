"""후속 고정 대조를 현재 v3와 같은 행·여섯 기준으로 다시 비교한다."""
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data_source import sha256_file as sha
from src.two_winter import validate
from src.extended_search import temperature_gate
from src.extended_comparison import block_sensitivity
from scripts.evaluate_method_blending import preservation


def read(p):return json.loads(p.read_text('utf-8'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')


def main():
    private=ROOT/'outputs/private';out=private/'followup_comparison_20261024_v1'
    if out.exists():raise FileExistsError('Preserve completed comparison')
    config=read(ROOT/'config/followup_temperature_20261024.json');gate=config['temperature_gate']
    refpath=ROOT/config['fixed_followup']['final_reference'];reference=validate(pd.read_parquet(refpath))
    for path,expected in config['reference_sha256'].items():assert sha(ROOT/path)==expected,path
    frozen=preservation();sources={};predictions={};metadata={};audit_files=[]
    for study,n in [('followup_temperature_20261024_v1',4),('followup_algorithm_20261024_v1',2)]:
        root=private/study;summary=read(root/'summary.json');assert len(summary['candidates'])==n
        plan=read(root/'plan.json');specs={s['name']:s for s in plan['settings']['candidates']}
        audit=private/(study.replace('_20261024_v1','_audit_20261024_v1'))/'receipt.json'
        verified=read(audit);assert len(verified['checks'])==n and verified['status']=='saved_models_replayed_and_verified'
        assert verified['plan_sha256']==sha(root/'plan.json')
        for check in verified['checks']:
            assert check['predictions_sha256']==sha(root/check['candidate']/'predictions.parquet')
            assert check['report_sha256']==sha(root/check['candidate']/'report.json')
        audit_files.append(str(audit.relative_to(ROOT)))
        for name in summary['candidates']:
            path=root/name/'predictions.parquet';predictions[name]=(validate(pd.read_parquet(path)),'prediction')
            sources[str(path.relative_to(ROOT))]=sha(path);metadata[name]=dict(kind='new_model',spec=specs[name],study=study)
    capacity=private/'followup_capacity_20261024_v1';extended=read(capacity/'summary.json')
    assert extended['status']=='fixed_followup_capacity_complete'
    if extended['candidates']:
        audit=private/'followup_capacity_audit_20261024_v1/receipt.json';verified=read(audit)
        assert len(verified['checks'])==len(extended['candidates']);audit_files.append(str(audit.relative_to(ROOT)))
    for name in extended['candidates']:
        path=capacity/name/'predictions.parquet';predictions[name]=(validate(pd.read_parquet(path)),'prediction')
        sources[str(path.relative_to(ROOT))]=sha(path);metadata[name]=dict(kind='extended_model',study=capacity.name)
    for name in extended['fixed_blends']:
        path=capacity/(name+'.parquet');predictions[name]=(validate(pd.read_parquet(path)),'prediction')
        sources[str(path.relative_to(ROOT))]=sha(path);metadata[name]=dict(kind='fixed_blend',study=capacity.name)
    offset_root=private/'followup_offset_20261024_v1';offset=read(offset_root/'summary.json')
    assert offset['status']=='nested_offset_comparison_complete' and offset['saved_model_replays']==6
    offset_audit=private/'followup_offset_audit_20261024_v1/receipt.json';verified=read(offset_audit)
    assert verified['status']=='nested_offset_independently_verified' and len(verified['fits'])==6
    assert verified['summary_sha256']==sha(offset_root/'summary.json')
    assert verified['predictions_sha256']==sha(offset_root/'predictions.parquet')
    audit_files.append(str(offset_audit.relative_to(ROOT)))
    offset_frame=validate(pd.read_parquet(offset_root/'predictions.parquet'))
    for policy in ['pooled_median','station_median']:
        name='nested_offset_'+policy;predictions[name]=(offset_frame,policy)
        metadata[name]=dict(kind='nested_calibration',study=offset_root.name,final_refit_offset=offset['final_refit_offsets'][policy])
    sources[str((offset_root/'predictions.parquet').relative_to(ROOT))]=sha(offset_root/'predictions.parquet')
    for name in ['solar_lgb_mae1200','solar_lgb_mse1200']:
        f,column=predictions[name];blended=reference.copy()
        pd.testing.assert_frame_equal(f[['station','time']],reference[['station','time']],check_exact=True)
        blended['prediction']=(f[column]+reference.prediction)/2
        predictions[name+'_equal_v3']=(blended,'prediction');metadata[name+'_equal_v3']=dict(kind='fixed_blend',components=[name,'v3'],weights=[.5,.5])
    mixed=reference.copy();mixed.prediction=(predictions['solar_lgb_mae1200'][0].prediction+predictions['solar_lgb_mse1200'][0].prediction)/2
    predictions['solar_lgb_l1_l2_equal']=(mixed,'prediction');metadata['solar_lgb_l1_l2_equal']=dict(kind='fixed_blend',components=['solar_lgb_mae1200','solar_lgb_mse1200'],weights=[.5,.5])
    icing=read(private/'icing_state_memory_20261024_v1/summary.json')
    state_audit=read(private/'icing_state_memory_audit_20261024_v1/receipt.json')
    assert state_audit['values']==4661655 and state_audit['summary_sha256']==sha(private/'icing_state_memory_20261024_v1/summary.json')
    memory_audit=read(private/'followup_long_memory_audit_20261024_v1/receipt.json');assert memory_audit['values']==6356360
    out.mkdir(parents=True);reports={};rows=[]
    for name,(frame,column) in predictions.items():
        pd.testing.assert_frame_equal(frame[['station','time','road_temp','ice']],reference[['station','time','road_temp','ice']],check_exact=True)
        report=temperature_gate(frame,frame[column],reference.prediction,gate);reports[name]=report
        saved=reference.copy();saved.prediction=frame[column].to_numpy();saved.to_parquet(out/(name+'.parquet'),index=False,compression='zstd')
        r=report['regression'];rows.append(dict(candidate=name,kind=metadata[name]['kind'],mae=r['pooled']['mae'],rmse=r['pooled']['rmse'],bias=r['pooled']['bias'],
            near_freezing_mae=r['near_freezing']['mae'],station_macro_mae=r['station_macro']['mae'],eligible=report['eligible'],**report['gates']))
    registry=pd.DataFrame(rows).sort_values('mae');registry.to_csv(out/'regression_registry.csv',index=False)
    eligible=registry.loc[registry.eligible,'candidate'].tolist();best=eligible[0] if eligible else None
    diagnostics={}
    for name in ([best] if best else [str(registry.iloc[0].candidate)]):
        frame,column=predictions[name];diagnostics[name]=block_sensitivity(frame,frame[column],reference.prediction)
    plt.rcParams.update({'font.family':'Malgun Gothic','axes.unicode_minus':False,'font.size':10})
    baseline_mae=float(np.abs(reference.prediction-reference.road_temp).mean())
    change=100*(1-registry.mae/baseline_mae)
    fig,ax=plt.subplots(figsize=(11,max(4.6,len(rows)*.38)),layout='constrained')
    ax.barh(registry.candidate,change,color=np.where(registry.eligible,'#087f8c','#a5b5be'))
    ax.axvline(0,color='#c07837',label=f'현재 v3: {baseline_mae:.6f}°C')
    ax.axvline(.5,color='#087f8c',linestyle='--',label='자체 통합 개선 기준 0.5%')
    span=max(1.,float(change.max()-change.min()))
    for index,value in enumerate(change):
        ax.text(value+(.035*span if value>=0 else -.035*span),index,f'{value:+.2f}%',
                ha='left' if value>=0 else 'right',va='center',fontsize=9)
    ax.set_xlim(min(0,float(change.min()))-.22*span,max(.5,float(change.max()))+.22*span)
    ax.invert_yaxis();ax.set_xlabel('같은 지역 제외 개발 MAE 감소율 (%, 양수이면 개선)')
    ax.set_title('추가 대조의 이득과 손실 · 반복 개발 비교')
    ax.legend(loc='lower right',fontsize=9);ax.spines[['top','right']].set_visible(False)
    fig.savefig(out/'followup_mae.png',dpi=170);plt.close(fig)
    assert preservation()==frozen
    write(out/'summary.json',dict(status='followup_comparison_complete',reference_mae=1.1456977458325481,
        reports=reports,metadata=metadata,temperature_eligible=eligible,provisional_best=best,
        decision='requires_robustness_and_runtime_verification' if best else 'preserve_v3_temperature',
        icing_eligible=icing['eligible'],icing_decision='requires_independent_adoption_review' if icing['eligible'] else 'preserve_v3_icing',
        diagnostics=diagnostics,source_sha256=sources,audit_files=audit_files,
        protected_labels_read=False,new_independent_assessment=False,production_model_changed=False,frozen_counts=list(frozen)))
    print(registry[['candidate','mae','eligible']].to_string(index=False),flush=True)
    print('Provisional best',best,'icing eligible',icing['eligible'],flush=True)


if __name__=='__main__':main()
