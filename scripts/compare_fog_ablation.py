"""시정 추가 전후의 동일 개발 OOF 행·라벨을 확인하고 지점/센서별 차이를 기록한다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import sha256_file
from src.validation import assert_training_stations, binary_metrics


def main():
    private = ROOT / "outputs/private"
    variants = {"fallback": "ice_fallback_logistic", "fog": "ice_fog_logistic"}
    predictions, summaries, hashes = {}, {}, {}
    for label, folder in variants.items():
        path = private / folder / "predictions.parquet"
        frame = pd.read_parquet(path).sort_values(["station", "time"]).reset_index(drop=True)
        assert_training_stations(frame.station.unique())
        if frame.duplicated(["station", "time"]).any():
            raise ValueError("Duplicate OOF target")
        predictions[label] = frame
        summaries[label] = json.loads((private / folder / "summary.json").read_text(encoding="utf-8"))
        hashes[label] = sha256_file(path)
    pd.testing.assert_frame_equal(predictions["fallback"][["station", "time", "ice"]],
                                  predictions["fog"][["station", "time", "ice"]])
    if summaries["fallback"]["archive_sha256"] != summaries["fog"]["archive_sha256"]:
        raise ValueError("Different archive versions")
    threshold_tables = [pd.read_csv(private / folder / "thresholds.csv") for folder in variants.values()]
    columns = ["held_out_station", "inner_train_rows", "inner_positive_slots", "validation_rows", "validation_positive_slots"]
    pd.testing.assert_frame_equal(threshold_tables[0][columns], threshold_tables[1][columns])
    metadata = pd.read_csv(private / "sensor_availability/metadata.csv", dtype={"station": str})
    metadata = metadata.loc[metadata.kind.eq("RWIS"), ["station", "station_type"]]
    rows = []
    for variant, frame in predictions.items():
        frame = frame.merge(metadata, on="station", how="left", validate="many_to_one")
        if frame.station_type.isna().any():
            raise ValueError("Missing sensor-type metadata")
        for axis in ["station", "station_type", "route"]:
            for value, part in frame.groupby(axis):
                valid = part.loc[part.ice.notna()]
                rows.append({"variant": variant, "group_axis": axis, "group": str(value).strip(),
                             "rows": len(valid), "ice_slots": int(valid.ice.sum()),
                             **binary_metrics(valid.ice.astype(int), valid.predicted_ice.astype(int))})
    summary = {"status": "paired_development_fog_ablation_not_official_evaluation",
               "target_rows": len(predictions["fog"]), "prediction_sha256": hashes,
               "slot_metrics": {key: value["slot_micro"] for key, value in summaries.items()},
               "daily_metrics": {key: value["daily_10minute_station_macro"] for key, value in summaries.items()},
               "limitations": ["Fixed logistic C=0.1; each variant selects its own threshold from identical inner folds.",
                               "Fog input uses prior observations with zero publication-delay assumption.",
                               "Honam has no fog input; same-route sources may be far from targets.",
                               "Sensor-type subgroup uses development stations only; no official held-out target opened.",
                               "Daily complete-day and undefined-metric policies remain provisional."]}
    out = private / "ice_fog_comparison"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "group_metrics.csv", index=False, encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
