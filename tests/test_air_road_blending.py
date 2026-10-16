import copy
import unittest
import numpy as np
import pandas as pd
from src.air_road_blending import predict_policy,consecutive,validate_model_origin,event_context,event_report,eligible,select_policy


def frame():
    return pd.DataFrame({'station':'12207','time':pd.date_range('2024-11-01',periods=8,freq='10min'),
        'asos_air_temp':-1.,'road_prediction':1.,'aws_air_temp':-1.,'aws_dewpoint':-1.,'aws_humidity':90.,
        'rain15_max_3h':0.,'asos_snow_cm':0.,'ice':[0,1,0,1,1,0,0,0]})


class AirRoadTests(unittest.TestCase):
    def test_consecutive_gate_is_causal_and_resets_at_missing_slots(self):
        f=frame(); f.loc[4:,'time']+=pd.Timedelta(minutes=10)
        np.testing.assert_array_equal(consecutive(f,np.ones(8,bool),3),[0,0,1,1,0,0,1,1])
        np.testing.assert_array_equal(consecutive(f.iloc[:4],np.ones(4,bool),3),[0,0,1,1])

    def test_future_rows_and_labels_cannot_change_earlier_policy(self):
        f=frame();spec=dict(source='air',threshold=0.,moisture='humidity80',slots=3,union=True)
        expected=predict_policy(f.iloc[:4],spec)
        f.loc[4:,'asos_air_temp']=20.;f['ice']=1-f.ice
        np.testing.assert_array_equal(predict_policy(f,spec)[:4],expected)

    def test_mean_source_missing_input_and_union_are_distinct(self):
        f=frame();f['road_prediction']=3.
        spec=dict(source='mean_air_road',threshold=0.,moisture='none',slots=1,union=False)
        self.assertFalse(predict_policy(f,spec).any())
        spec['source']='air';self.assertTrue(predict_policy(f,spec).all())
        f.loc[0,'asos_air_temp']=np.nan;self.assertEqual(predict_policy(f,spec)[0],0)
        f.loc[0,'road_prediction']=-1.;spec['union']=True
        self.assertEqual(predict_policy(f,spec)[0],1)

    def test_inner_temperature_requires_both_excluded_groups(self):
        groups={'A':['12207'],'B':['12408'],'C':['23205'],'D':['23404']}
        record={'excluded_groups':['B'],'forbidden_stations':['12408'],'training_stations':['12207']}
        with self.assertRaises(ValueError):validate_model_origin(record,groups,'A','B')
        record.update(excluded_groups=['A','B'],forbidden_stations=['12207','12408'],training_stations=['23205'])
        validate_model_origin(record,groups,'A','B')

    def test_event_gain_cannot_hide_loss_of_a_single_slot_event(self):
        f=frame();context=event_context(f,[0,1,0,0,0,0,0,0])
        r=event_report(context,[0,0,0,1,1,0,0,0])
        self.assertEqual((r['lost_events'],r['gained_events'],r['lost_single_slot_events']),(1,1,1))

    def report(self,f1,fp,fn=1):
        return {'daily':{n:{'f1_available_station_mean':f1,'precision_available_station_mean':f1,'recall_available_station_mean':f1} for n in ['144','1']},
            'fp':fp,'fn':fn,'station_tp':{'12207':2},'event':{'lost_events':0}}

    def test_research_tradeoff_does_not_pass_strict_gate(self):
        refs={name:self.report(.1,20 if name=='current' else 100) for name in ['current','air_zero','always_one']}
        candidate=self.report(.2,80)
        self.assertTrue(eligible(candidate,refs,'research'));self.assertFalse(eligible(candidate,refs,'strict'))
        candidate['event']['lost_events']=1;self.assertFalse(eligible(candidate,refs,'research'))

    def test_null_score_and_outer_group_selection_are_rejected(self):
        refs={name:self.report(.1,100) for name in ['current','air_zero','always_one']}
        candidate=self.report(None,10)
        self.assertFalse(eligible(candidate,refs,'research'))
        with self.assertRaises(ValueError):select_policy({'x':candidate},refs,'research','A',['A','B','C'])
