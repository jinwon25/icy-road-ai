import pytest
from src.rwis_response_quality import quarantine_duplicates
from src.kma_rwis_download import parse_observations


HEADER='\n'.join(f'# {i}. {n} : field' for i,n in enumerate(['TM','STN_ID','LAT','LON','HT','SFS','TR1'],1))+'\n'


def row(t='202602130010',state='01',temperature='1.2',station='33406'):
    return f'{t},{station},36.7988,127.5074,10,{state},{temperature}\n'


def test_identical_rows_collapse_but_conflicting_targets_all_quarantined():
    body=HEADER+row()+row()+row('202602130020','01')+row('202602130020','04')+'#7777END\n'
    clean,r=quarantine_duplicates(body,'33406')
    assert r['identical_duplicate_rows_removed']==1 and r['conflicting_keys']==1 and r['conflicting_rows_removed']==2
    f=parse_observations(clean,'33406','2026-02-13','2026-02-13 23:59')
    assert len(f)==1 and f.time.iloc[0].minute==10


def test_non_target_conflicts_are_equally_quarantined():
    clean,r=quarantine_duplicates(HEADER+row(temperature='1.2')+row(temperature='1.3'),'33406')
    assert r['conflicting_keys']==1 and r['remaining_rows']==0
    assert parse_observations(clean,'33406','2026-02-13','2026-02-13 23:59').empty


def test_missing_timestamps_preserved_for_original_parser_and_station_guard():
    body=HEADER+row('0')+row('0')
    clean,r=quarantine_duplicates(body,'33406');assert clean==body and r['conflicting_keys']==0
    with pytest.raises(ValueError):quarantine_duplicates(HEADER+row(station='23411'),'33406')
    with pytest.raises(ValueError):quarantine_duplicates(HEADER,'33411')
