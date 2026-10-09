import unittest
import numpy as np
import pandas as pd
from src.regularized_ice import make_model, fit_converged, SPLINE_COLUMNS


class RegularizedIceTests(unittest.TestCase):
    def test_training_only_preprocessing_and_empty_input(self):
        rng = np.random.default_rng(42)
        data = pd.DataFrame(rng.normal(size=(200, 4)), columns=SPLINE_COLUMNS)
        data.aws_humidity = 70 + 10 * data.aws_humidity
        data["empty_reference"] = np.nan
        data.loc[0, "near_road_temp"] = np.nan
        columns = list(data.columns)
        config = {"C": .1, "positive_weight": 20., "max_iter": 1000, "tol": 1e-5}
        labels = (data.aws_air_temp < -.7).astype(int)
        for kind in ["linear", "spline"]:
            model = fit_converged(make_model(columns, kind, config), data, labels)
            before = model.named_steps["scale"].mean_.copy()
            scores = model.predict_proba(data.iloc[:10])[:, 1]
            changed = data.iloc[:10].copy();changed.aws_air_temp = 100
            model.predict_proba(changed)
            np.testing.assert_array_equal(model.named_steps["scale"].mean_, before)
            self.assertTrue(np.isfinite(scores).all())
            self.assertTrue(((scores >= 0) & (scores <= 1)).all())

    def test_target_labels_rejected(self):
        config = {"C": .1, "positive_weight": 20., "max_iter": 1000, "tol": 1e-5}
        for kind in ["linear", "spline"]:
            with self.assertRaises(ValueError):
                make_model([*SPLINE_COLUMNS, "ice"], kind, config)


if __name__ == "__main__":
    unittest.main()
