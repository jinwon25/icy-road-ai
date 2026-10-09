"""과거 주변 상태 모델의 전체 예측·내부 임계값·참조 격리를 감사한다."""
import json
import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, average_precision_score, roc_auc_score
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.frozen_assessment import verify_freeze
from src.physical_features import load_thermal_sources
from src.surface_state_context_v2 import SurfaceStateContextV2, STATE_FEATURES
from src.validation import assert_training_stations, PROTECTED_STATIONS
from scripts.baseline_ice_logistic import choose_threshold


def main():
    private = ROOT / "outputs/private"
    out = private / "surface_state_v2_forward"
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    config = summary["config"]
    data = pd.read_parquet(private / "physical_features/features.parquet").reset_index(drop=True)
    result = pd.read_parquet(out / "predictions.parquet").sort_values(["station", "time"]).reset_index(drop=True)
    baseline = pd.read_parquet(private / "forward_physics/predictions.parquet").sort_values(["station", "time"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(result[["station", "time", "ice"]], baseline[["station", "time", "ice"]])
    assert_training_stations(result.station.unique())
    if result.duplicated(["station", "time"]).any() or len(result.station.unique()) != 14:
        raise AssertionError("Invalid development prediction grid")
    meta = pd.read_csv(private / "sensor_availability/metadata.csv", dtype={"station": str})
    meta = meta.loc[meta.kind.eq("RWIS"), ["station", "route", "lat", "lon"]]
    context = SurfaceStateContextV2(data, load_thermal_sources(competition_archive(ROOT)), meta, data[["station", "time", "state_raw"]].copy())
    reference_count = model_count = 0
    verified_rows = 0
    with threadpool_limits(limits=2):
        for held in sorted(result.station.unique()):
            folder = out / str(held)
            inner = pd.read_parquet(folder / "inner_oof.parquet")
            if inner.station.eq(held).any() or inner.station.isin(PROTECTED_STATIONS).any() or inner.time.max() >= pd.Timestamp(config["train_before"]):
                raise AssertionError("Inner partition leakage")
            references = json.loads((folder / "references.json").read_text(encoding="utf-8"))
            for reference in references:
                if held not in reference["forbidden"] or reference["source"] in set(reference["forbidden"]) | {reference["target"]} | PROTECTED_STATIONS:
                    raise AssertionError("Forbidden reference")
                reference_count += 1
            valid = data.loc[data.station.eq(held) & data.time.ge(config["validate_from"])].copy()
            additional, _ = context.features(valid, {held})
            valid_x = pd.concat([valid, additional], axis=1)
            expected = result.loc[result.station.eq(held)].set_index("time").loc[valid.time]
            choices = json.loads((folder / "thresholds.json").read_text(encoding="utf-8"))
            for choice in choices:
                name = choice["candidate"]
                columns = summary["feature_sets"][name]
                if set(columns) & {"ice", "state_raw", "station", "time"}:
                    raise AssertionError("Forbidden model feature")
                model = joblib.load(folder / f"{name}_development_model.joblib")
                score = model.predict_proba(valid_x[columns])[:, 1]
                np.testing.assert_allclose(score, expected[f"score_{name}"], rtol=0, atol=1e-12)
                if model.n_iter_ != config["model"]["max_iter"]:
                    raise AssertionError("Unexpected boosting iteration count")
                threshold, f1 = choose_threshold(inner.ice.to_numpy(dtype=int), inner[f"score_{name}"].to_numpy())
                np.testing.assert_allclose([threshold, f1], [choice["slot_threshold"], choice["inner_slot_f1"]], rtol=0, atol=1e-12)
                trace = pd.read_csv(folder / f"{name}_trace.csv")
                best = trace.loc[np.isclose(trace.station_daily_f1, trace.station_daily_f1.max(), rtol=0, atol=1e-12)].iloc[-1]
                np.testing.assert_allclose([best.threshold, best.station_daily_f1], [choice["daily_threshold"], choice["inner_daily_f1"]], rtol=0, atol=1e-12)
                for policy in ["slot", "daily"]:
                    np.testing.assert_array_equal(expected[f"pred_{policy}_{name}"], score >= choice[f"{policy}_threshold"])
                model_count += 1
                verified_rows += len(valid)
    valid = result.loc[result.ice.notna()]
    for key, metrics in summary["metrics"].items():
        name, policy = key.rsplit("_", 1)
        score, predicted = valid[f"score_{name}"], valid[f"pred_{policy}_{name}"]
        tn, fp, fn, tp = confusion_matrix(valid.ice, predicted, labels=[0, 1]).ravel()
        if (tn, fp, fn, tp) != tuple(metrics["slot_micro"][k] for k in ["tn", "fp", "fn", "tp"]):
            raise AssertionError("Confusion matrix differs")
        np.testing.assert_allclose([average_precision_score(valid.ice, score), roc_auc_score(valid.ice, score)],
                                   [metrics["average_precision"], metrics["roc_auc"]], rtol=0, atol=1e-15)
    known = data.aws_source_time.notna()
    if not (data.loc[known, "aws_source_time"] < data.loc[known, "time"]).all():
        raise AssertionError("Future AWS source")
    frozen = verify_freeze(ROOT)
    audit = {"status": "surface_state_v2_forward_audit_passed", "models_reloaded": model_count,
             "score_rows_recomputed": verified_rows, "valid_target_rows": len(valid), "ice_slots": int(valid.ice.sum()),
             "reference_records_checked": reference_count, "threshold_choices_verified": True,
             "confusion_ap_roc_recomputed": True, "frozen_files_unchanged": len(frozen["files"]),
             "protected_data_used": False, "summary_sha256": sha256_file(out / "summary.json"),
             "predictions_sha256": sha256_file(out / "predictions.parquet"),
             "baseline_predictions_sha256": sha256_file(private / "forward_physics/predictions.parquet")}
    (out / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
