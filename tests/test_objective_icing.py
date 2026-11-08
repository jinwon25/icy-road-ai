import numpy as np
import pandas as pd
import pytest
import torch

from src.anchored_icing import ASOS_FEATURES
from src.objective_icing import features, fit_preprocessor, transform, group_data, soft_loss, data_loss, predictions, choose, fit, correction


def frame():
    f = pd.DataFrame({'station': ['a']*288 + ['b']*144,
        'winter': 2024, 'time': list(pd.date_range('2024-11-01', periods=288, freq='10min')) + list(pd.date_range('2024-11-01', periods=144, freq='10min')),
        'ice': np.r_[np.ones(2), np.zeros(142), np.ones(1), np.zeros(143), np.ones(1), np.zeros(143)]})
    for column in ASOS_FEATURES:
        f[column] = 1.
    return f


def test_features_ignore_targets_identity_and_other_rows():
    f = frame()
    a = features(f)
    f.ice = 1-f.ice
    f.station = 'different'
    f['road_temp'] = 1000.
    pd.testing.assert_frame_equal(a, features(f))
    f.loc[2:, ASOS_FEATURES] = 999.
    pd.testing.assert_frame_equal(a.iloc[:2], features(f).iloc[:2])


def test_preprocessor_uses_training_only_and_keeps_missing_indicator():
    train = np.array([[1., np.nan], [3., np.nan]])
    state = fit_preprocessor(train)
    query = transform(np.array([[1000., 2.], [np.nan, np.nan]]), state)
    np.testing.assert_equal(state['medians'], [2., 0.])
    np.testing.assert_equal(query, [[8., 2., 0., 0.], [0., 0., 1., 1.]])


def test_day_soft_loss_gives_equal_station_winter_mass():
    group = group_data(frame())
    np.testing.assert_allclose(group['day_weights'], [.25, .25, .5])
    for station in [0,1]:
        assert np.isclose(group['row_weights'][group['station_ids']==station].sum(), 216)
    partial = group_data(frame().iloc[1:])
    assert partial['day_weights'][0] == 0


def test_soft_loss_matches_manual_group_confusion_and_has_gradients():
    p = torch.tensor([.7,.2,.4,.6], requires_grad=True)
    y = torch.tensor([1.,0.,1.,0.])
    ids = torch.tensor([0,0,1,1]); weights = torch.tensor([.5,.5])
    loss = soft_loss(p,y,ids,weights)
    assert np.isclose(float(loss.detach()), .5*(1-1.4/1.9)+.5*(1-.8/2.))
    loss.backward()
    assert torch.isfinite(p.grad).all()
    assert p.grad[0] < 0 and p.grad[1] > 0


@pytest.mark.parametrize('kind', ['bce_day','focal_day','soft_station','soft_day'])
def test_loss_finite_for_all_negative_training(kind):
    f = frame(); f.ice = 0
    group = {k:torch.tensor(v,dtype=torch.long if k.endswith('_ids') else torch.float32) for k,v in group_data(f).items()}
    logits = torch.zeros(len(f), requires_grad=True)
    loss=data_loss(logits,torch.zeros(len(f)),group,kind)
    loss.backward()
    assert torch.isfinite(loss) and torch.isfinite(logits.grad).all()


def test_prediction_mask_and_bounded_correction():
    f=pd.DataFrame({'asos_air_temp':[-3.,-.5,1.,3.], 'available':[True,True,False,True], 'fit':[99.,-99.,99.,99.]})
    specs=[dict(model=None,offset=0),dict(model='fit',offset=1)]
    np.testing.assert_equal(predictions(f,specs), [[1,1],[1,0],[np.nan,np.nan],[0,0]])


def test_selection_keeps_recall_guard_and_baseline_tie():
    table=pd.DataFrame([dict(candidate='asos_zero',model=None,f1=.1,recall=.9,f1_2024=.1,f1_2025=.1,complexity=0),
                        dict(candidate='fit',model='soft_day',f1=.2,recall=.5,f1_2024=.2,f1_2025=.2,complexity=2)])
    assert choose(table,'mean_f1')=='fit'
    assert choose(table,'recall_guard')=='asos_zero'
    table.loc[1,'f1']=.1
    assert choose(table,'mean_f1')=='asos_zero'


def test_fitted_model_roundtrip_needs_no_pickle(tmp_path):
    f=frame();settings=dict(steps=2,learning_rate=.03,l2=.001,cap_c=2)
    model=fit(f,'soft_day',settings)
    path=tmp_path/'model.npz';np.savez_compressed(path,**model)
    with np.load(path,allow_pickle=False) as archive:loaded=dict(archive)
    np.testing.assert_array_equal(correction(f,loaded),correction(f,model))


def test_fixed_calendar_does_not_reward_removing_false_alarm_days():
    from scripts.evaluate_objective_icing import fixed_calendar_f1
    baseline=pd.DataFrame({'station':['a','a','b','b'],'date_kst':[1,2,1,2],'f1':[0.,1.,np.nan,np.nan]})
    candidate=baseline.copy();candidate.loc[0,'f1']=np.nan
    assert candidate.loc[candidate.station.eq('a'),'f1'].mean()==1
    assert fixed_calendar_f1(candidate,baseline)==.25
    with pytest.raises(AssertionError):fixed_calendar_f1(candidate.iloc[::-1],baseline)


def test_preservation_allows_only_known_archived_collector(tmp_path,monkeypatch):
    import json
    from scripts import evaluate_objective_icing as run
    from src.data_source import sha256_file
    (tmp_path/'scripts').mkdir();(tmp_path/'src').mkdir()
    source=tmp_path/'src/model.py';source.write_text('original',encoding='utf8')
    collector=tmp_path/'scripts/review_official_updates.py';collector.write_text('original',encoding='utf8')
    saved=tmp_path/'outputs/private/submission_candidate_20261026_v7/scripts/review_official_updates.py'
    saved.parent.mkdir(parents=True);saved.write_bytes(collector.read_bytes())
    folder=tmp_path/'seal';folder.mkdir()
    seal={'files':{},'code_signatures':{str(p.relative_to(tmp_path)).replace('\\','/'):sha256_file(p) for p in [source,collector]}}
    (folder/'prediction_seal.json').write_text(json.dumps(seal),encoding='utf8')
    (folder/'input_signatures.json').write_text('{}',encoding='utf8')
    monkeypatch.setattr(run,'ROOT',tmp_path);monkeypatch.setattr(run,'DEFAULT',folder)
    monkeypatch.setattr(run,'old_freezes',lambda:(47,549))
    collector.write_text('documented update',encoding='utf8')
    assert len(run.verify_preserved()['archived_code'])==1
    source.write_text('unapproved model change',encoding='utf8')
    with pytest.raises(AssertionError):run.verify_preserved()
