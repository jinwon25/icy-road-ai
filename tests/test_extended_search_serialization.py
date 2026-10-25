import json
import numpy as np
import pytest
from scripts.resume_extended_search import write


def test_nan_model_parameter_has_explicit_tag_but_metrics_stay_strict(tmp_path):
    p=tmp_path/'receipt.json'
    write(p,{'parameters':{'missing':np.nan},'mae':1.2})
    assert json.loads(p.read_text('utf-8'))['parameters']['missing']=={'nonfinite_float':'nan'}
    write(p,{'fits':[{'parameters':{'missing':np.nan}}]})
    assert json.loads(p.read_text('utf-8'))['fits'][0]['parameters']['missing']=={'nonfinite_float':'nan'}
    with pytest.raises(ValueError):write(tmp_path/'invalid.json',{'mae':np.nan})
