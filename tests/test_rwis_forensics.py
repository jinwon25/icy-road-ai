import pytest
from src.rwis_forensics import response_profile

HEADER='# 1. TM : time\n# 2. STN_ID : station\n# 3. SFS : state\n# 4. TR1 : temp\n'


def test_missing_plus_valid_is_recorded_as_conflict_without_resolving_label():
    body=HEADER+'202602130010,33406,-999,-1.3\n202602130010,33406,2,-1.3\n0,33406,-999,-999\n'
    r=response_profile(body,'33406','2026-02-13','2026-02-13 01:00')
    assert r['conflicting_state_pairs']=={'-999|2':1} and r['differing_fields']=={'SFS':1}
    assert r['ten_minute_categories']=={'202602130010':'conflict_quarantine'} and r['invalid_timestamp_tokens']=={'0':1}


def test_profiles_refuse_wrong_station_or_outside_range():
    with pytest.raises(ValueError):response_profile(HEADER+'202602130010,23411,1,1','33406','2026-02-13','2026-02-14')
    with pytest.raises(ValueError):response_profile(HEADER+'202602150010,33406,1,1','33406','2026-02-13','2026-02-14')
    with pytest.raises(ValueError):response_profile(HEADER,'33411','2026-02-13','2026-02-14')
