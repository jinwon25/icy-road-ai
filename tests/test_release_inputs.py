import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

from src.observation_io import daily_kind, daily_members, numeric_observations, read_columns
from src.weather_features import _load_daily
from scripts.prepare_release_workspace import prepare_workspace
from scripts.compare_data_releases import compare, COLUMNS


class ReleaseInputTests(unittest.TestCase):
    def test_fog_and_road_files_with_identical_basenames_stay_separate(self):
        with zipfile.ZipFile(io.BytesIO(), "w") as archive:
            road = "1. road/Jeonbuk_RWIS_daily_20241101.csv"
            fog = "1-1. fog/Jeonbuk_RWIS_daily_20241101.csv"
            archive.writestr(road, "관측 지점번호,관측소 종류,관측소 고도 (m),노면온도 (광학)\n12103,ice,100,-2\n")
            archive.writestr(fog, "관측 지점번호,시정 (m)\n12306,500\n")
            archive.writestr("Jeonbuk_aws_daily_20241101.csv", "time,station\n")
            self.assertEqual(daily_members(archive, "RWIS"), [road])
            self.assertEqual(daily_members(archive, "FOG"), [fog])
            self.assertEqual(len(daily_members(archive, "AWS")), 1)
            frame = _load_daily(archive, "RWIS", ["노면온도 (광학)", "관측 지점번호"],
                                ["road_temp", "station"], None)
            self.assertEqual(frame.iloc[0].tolist(), ["-2", "12103"])
            with self.assertRaises(ValueError):
                read_columns(archive, fog, ["노면온도 (광학)"], ["road_temp"])

    def test_official_sentinels_do_not_erase_valid_negative_temperatures(self):
        result = numeric_observations(pd.Series(["-999", "-99.9", " -99.20 ", "-99.7", "", "x", "inf", "-2.1", "0", "12.0"]))
        self.assertTrue(result.iloc[:7].isna().all())
        self.assertEqual(result.iloc[7:].tolist(), [-2.1, 0, 12])

    def test_workspace_preserves_old_cache_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outputs/private").mkdir(parents=True)
            old = root / "outputs/private/old.txt"
            old.write_text("old", encoding="utf-8")
            archive = root / "new.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                for kind in ("RWIS", "ASOS", "aws"):
                    zipped.writestr(f"Jeonbuk_{kind}_daily_20241101.csv", "header\n")
            dest = prepare_workspace(root, archive, "20261007")
            self.assertEqual(old.read_text(), "old")
            self.assertFalse((dest / "outputs").exists())
            self.assertEqual((dest / "new.zip").read_bytes(), archive.read_bytes())
            with self.assertRaises(FileExistsError):
                prepare_workspace(root, archive, "20261007")
            with self.assertRaises(ValueError):
                prepare_workspace(root, archive, "../invalid")

    def test_release_comparison_excludes_protected_values_and_reports_label_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("old.zip", "new.zip")]
            for index, path in enumerate(paths):
                rows = [["2024-11-01 00:00:00", "12103", "13.1" if index == 0 else "13", "-1", "80", "0", "1"],
                        ["2024-11-01 00:00:00", "12410.0", "4" if index == 0 else "1", str(index * 20), "80", "0", "1"]]
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("1. road/Jeonbuk_RWIS_daily_20241101.csv",
                                     pd.DataFrame(rows, columns=COLUMNS).to_csv(index=False))
            result = compare(*paths)
            self.assertEqual(result["key_counts"]["both"], 1)
            self.assertEqual(result["changed_values_on_shared_keys"]["road_temp"], 0)
            self.assertEqual(result["label_transitions_on_shared_keys_minus1_is_unknown"], {"-1->0": 1})


if __name__ == "__main__":
    unittest.main()
