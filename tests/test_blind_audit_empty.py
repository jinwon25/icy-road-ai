import pandas as pd
from scripts.audit_blind_icing_empty_adapter import typed_empty_time


def test_empty_time_cast_changes_no_observations_and_preserves_original():
    original=pd.DataFrame(columns=['station','time','ice'])
    result=typed_empty_time(original)
    assert result.empty and original.empty and result.time.dtype.kind=='M' and original.time.dtype.kind=='O'
    assert (result.time.dt.minute%10==0).all()


def test_nonempty_audit_input_is_unchanged():
    original=pd.DataFrame({'time':pd.to_datetime(['2026-02-13']),'ice':[1.]})
    assert typed_empty_time(original) is original
