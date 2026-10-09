import unittest
from src.kma_station_catalog import parse_catalog, select_candidates


class KmaCatalogTests(unittest.TestCase):
    def test_aliases_and_protected_station_exclusion(self):
        raw = '\n'.join(['33413 서상126(도) 통영-대전선 목표(결빙) 425m 35.6681 127.6718',
                         '33411 삼봉(도) 통영-대전선 목표(결빙) 439m 35.7167 127.6149',
                         '33312 잠두교(도) 통영-대전중부 목표(안개) 212m 36.0847 127.6098',
                         '12103 군산휴(도) 서해안 거점 33m 36.0201 126.7958'])
        catalog = parse_catalog(raw); annotated, selected = select_candidates(catalog, ['12103.0'])
        self.assertEqual(selected.station.tolist(), ['33413'])
        self.assertEqual(selected.iloc[0].route, '통영-대전중부')
        self.assertEqual(selected.iloc[0].route_raw, '통영-대전선')
        self.assertTrue(annotated.loc[annotated.station.eq('33411'), 'already_in_competition_scope'].all())

    def test_duplicate_and_malformed_catalog_rejected(self):
        line = '33413 서상126(도) 통영-대전선 목표(결빙) 425m 35.6681 127.6718'
        with self.assertRaises(ValueError): parse_catalog(line+'\n'+line)
        with self.assertRaises(ValueError): parse_catalog('33413 누락된 행')
        with self.assertRaises(ValueError): parse_catalog(line.replace('35.6681', '0.0'))


if __name__ == '__main__': unittest.main()
