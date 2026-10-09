from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
from scripts.fresh_station_validation import verify_seal,ensure_unopened,temperature_report
import pandas as pd,numpy as np
from scripts.audit_joint_surface import sha
from src.kma_rwis_download import validate_development_request


class FreshValidationTests(unittest.TestCase):
    def test_empty_temperature_station_remains_visible_with_its_denominator(self):
        f=pd.DataFrame({'station':['12206','12407'],'road_temp':[1.,np.nan]})
        r=temperature_report(f,[2.,3.]);self.assertEqual(r['stations']['12407']['n'],0);self.assertIsNone(r['stations']['12407']['mae'])
        self.assertEqual(r['station_macro']['mae'],1.);self.assertEqual(r['stations_with_valid_temperature'],1)
    def test_already_requested_station_blocks_new_blind_sealing(self):
        with TemporaryDirectory() as tmp:
            ensure_unopened(tmp,{'12206'})
            p=Path(tmp)/'download_manifest.json';p.write_text(json.dumps({'records':{'a':{'station':'12206'}}}),'utf-8')
            with self.assertRaises(ValueError):ensure_unopened(tmp,{'12206'})
            ensure_unopened(tmp,{'12407'})
    def test_plan_rejects_official_original_external_and_next_winter_queries(self):
        r=Path(__file__).resolve().parents[1];p=json.loads((r/'config/fresh_station_validation.json').read_text('utf-8'))
        previous=json.loads((r/'config/kma_external_validation_plan.json').read_text('utf-8'))
        ids=set().union(*map(set,p['station_groups'].values()));self.assertEqual(len(ids),8)
        self.assertFalse(ids&set(previous['competition_stations_excluded_from_external_requests']))
        self.assertFalse(ids&set().union(*map(set,previous['station_groups'].values())))
        validate_development_request(p,'12206','2024-11-01','2024-11-01 11:59')
        for station,time in [('12410','2024-11-01'),('33411','2024-11-01'),('23402','2024-11-01'),('33408','2024-11-01'),('12206','2025-11-01')]:
            with self.assertRaises(ValueError):validate_development_request(p,station,time,time)
    def test_frozen_predictions_and_sources_detect_any_mutation(self):
        with TemporaryDirectory() as tmp:
            out=Path(tmp);source=out/'input.txt';source.write_text('original','utf-8');prediction=out/'predictions.txt';prediction.write_text('fixed','utf-8')
            sig=out/'input_signature.json';sig.write_text(json.dumps({'source':{'path':str(source),'sha256':sha(source)}}),'utf-8')
            seal={'new_outcomes_present_at_seal':False,'files':{'predictions.txt':sha(prediction),'input_signature.json':sha(sig)}}
            (out/'prediction_seal.json').write_text(json.dumps(seal),'utf-8');verify_seal(out)
            prediction.write_text('changed','utf-8')
            with self.assertRaises(AssertionError):verify_seal(out)
            prediction.write_text('fixed','utf-8');source.write_text('changed','utf-8')
            with self.assertRaises(AssertionError):verify_seal(out)


if __name__=='__main__':unittest.main()
