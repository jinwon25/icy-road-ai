import pandas as pd
from scripts.screen_expanded_icing_regions import unused_candidates


def test_only_target_routes_unopened_noncompetition_nonprotected():
    roads = pd.DataFrame(dict(station=['new','other_route','queried','competition','12410','no_state'],
        independent_station_candidate=[True,True,True,True,True,False],
        target_route_candidate=[True,False,True,True,True,True],
        already_in_competition_scope=[False,False,False,True,False,False]))
    assert unused_candidates(roads, {'queried'}).station.tolist() == ['new']
