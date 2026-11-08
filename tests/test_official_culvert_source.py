from scripts.prepare_official_culvert_anchors import equivalent_value


def test_numeric_csv_rounding_does_not_hide_missing_or_large_mismatch():
    assert equivalent_value('126.970','126.969999999999999',True)
    assert equivalent_value('37.123456789','37.1234567894',True)
    assert not equivalent_value('37.123456789','37.123456790',True)
    assert not equivalent_value('126.970','126.971',True)
    assert equivalent_value('','***********',True)
    assert not equivalent_value('','0.000',True)
    assert not equivalent_value('0.000','********',True)
    assert equivalent_value('천안-230 ','천안-230')
    assert not equivalent_value('천안-230','천안-231')
