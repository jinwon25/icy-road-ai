import pandas as pd
import pytest
from scripts.fetch_expanded_asos_inputs import parse_weather, COLUMNS


def body(station='131', timestamp='202501010000'):
    return '# YYMMDDHHMI STN\n'+' '.join([timestamp,station]+['-9']*(len(COLUMNS)-2))+'\n#7777END\n'


def test_weather_error_page_truncation_wrong_station_and_date_rejected():
    start=end=pd.Timestamp('2025-01-01')
    for text in ['<html>403</html>', body().replace('#7777END',''), body('999'), body(timestamp='202601010000')]:
        with pytest.raises(ValueError):parse_weather(text, [131], start, end)
    parsed=parse_weather(body(),[131],start,end)
    assert len(parsed)==1 and parsed.TA.iloc[0]=='-9'
    with pytest.raises(ValueError):parse_weather(body()+body(),[131],start,end)
