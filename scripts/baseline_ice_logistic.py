"""Development-only direct Ice baseline with nested station-held-out thresholds."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.validation import (PROTECTED_STATIONS, assert_training_stations,
                            binary_metrics, daily_scores, macro_scores,
                            route_macro_scores)

FEATURES = ["asos_air_temp", "aws_air_temp", "aws_humidity", "aws_wind_speed",
            "aws_rain_15m", "aws_dewpoint", "aws_age_minutes", "asos_age_minutes",
            "aws_distance_km", "asos_distance_km", "hour_sin", "hour_cos",
            "season_sin", "season_cos"]


def add_time_features(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    time = pd.to_datetime(result.time)
    minute = time.dt.hour * 60 + time.dt.minute
    day = time.dt.dayofyear + minute / 1440
    result["hour_sin"] = np.sin(2 * np.pi * minute / 1440)
    result["hour_cos"] = np.cos(2 * np.pi * minute / 1440)
    result["season_sin"] = np.sin(2 * np.pi * day / 365.25)
    result["season_cos"] = np.cos(2 * np.pi * day / 365.25)
    return result


def make_model() -> object:
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
        StandardScaler(),
        LogisticRegression(C=0.1, class_weight="balanced", solver="liblinear",
                           max_iter=200, random_state=20260923),
    )


def choose_threshold(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    """Maximize pooled inner-OOF slot F1; break ties toward fewer alarms."""
    if int(labels.sum()) == 0:
        raise ValueError("No positive Ice labels in inner OOF data")
    precision, recall, thresholds = precision_recall_curve(labels, scores)
    f1 = np.divide(2 * precision[:-1] * recall[:-1],
                   precision[:-1] + recall[:-1],
                   out=np.zeros_like(thresholds),
                   where=(precision[:-1] + recall[:-1]) > 0)
    best = np.flatnonzero(np.isclose(f1, np.max(f1)))[-1]
    return float(thresholds[best]), float(f1[best])


def smoke_sample(data: pd.DataFrame) -> pd.DataFrame:
    """Preserve all positives; sample negatives per station for a fast flow check."""
    positive = data.loc[data.ice.eq(1)]
    samples = [group.sample(n=min(500, len(group)), random_state=20260923)
               for _, group in data.loc[data.ice.eq(0)].groupby("station")]
    negative = pd.concat(samples, ignore_index=True)
    return pd.concat([positive, negative], ignore_index=True)


def inner_oof(train: pd.DataFrame, folds: list[dict], features: list[str] | None = None) -> tuple[np.ndarray, np.ndarray]:
    features = FEATURES if features is None else features
    scores = np.full(len(train), np.nan)
    labels = train.ice.astype(int).to_numpy()
    for inner in folds:
        held = set(inner["stations"])
        fit_mask = ~train.station.isin(held).to_numpy()
        valid_mask = ~fit_mask
        if not fit_mask.any() or not valid_mask.any():
            raise ValueError("Empty internal station fold")
        fit = train.iloc[np.flatnonzero(fit_mask)]
        valid = train.iloc[np.flatnonzero(valid_mask)]
        if set(fit.station) & set(valid.station):
            raise AssertionError("Internal station leakage")
        model = make_model()
        model.fit(fit[features], fit.ice.astype(int))
        scores[valid_mask] = model.decision_function(valid[features])
    if not np.isfinite(scores).all():
        raise AssertionError("Inner OOF scores are incomplete")
    return labels, scores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true",
                        help="Two outer folds and sampled negative training rows")
    parser.add_argument("--variant", choices=("nearest", "fallback", "history", "fog"), default="nearest")
    args = parser.parse_args()
    private = ROOT / "outputs" / "private"
    input_name = "ice_features" if args.variant == "nearest" else "ice_fallback_features"
    data = add_time_features(pd.read_parquet(private / input_name / "features.parquet"))
    features = FEATURES.copy()
    if args.variant == "fog":
        from src.fog_features import FOG_FEATURES
        fog = pd.read_parquet(private / "ice_fog_features_delay0/features.parquet")
        if len(fog) != len(data) or fog.duplicated(["station", "time"]).any():
            raise ValueError("Fog cache denominator mismatch")
        check = data[["station", "time", "ice"]].merge(
            fog[["station", "time", "ice"]], on=["station", "time"],
            how="outer", validate="one_to_one", indicator=True, suffixes=("_base", "_fog"))
        if not check._merge.eq("both").all() or not check.ice_base.equals(check.ice_fog):
            raise ValueError("Fog cache targets or labels differ")
        data = data.merge(fog[["station", "time", *FOG_FEATURES]],
                          on=["station", "time"], how="left", validate="one_to_one")
        features += FOG_FEATURES
    if args.variant == "history":
        from scripts.audit_ice_weather_history import HISTORY
        history = pd.read_parquet(private / "ice_weather_history" / "features.parquet")
        history = history[["station", "time", *HISTORY]]
        data = data.merge(history, on=["station", "time"], how="left", validate="one_to_one")
        if data[HISTORY].isna().all(axis=1).sum() > data.aws_source_time.isna().sum():
            raise AssertionError("Prior AWS history unexpectedly unavailable")
        features += HISTORY
    data["station"] = data.station.astype(str)
    assert_training_stations(data.station.unique())
    if set(data.station) & PROTECTED_STATIONS:
        raise AssertionError("Protected RWIS entered Ice classifier")
    if data.duplicated(["station", "time"]).any():
        raise ValueError("Duplicate target station/time")
    splits = json.loads((private / "validation" / "splits.json").read_text(encoding="utf-8"))
    folds = splits["outer_folds"][:2] if args.smoke else splits["outer_folds"]
    outputs = []
    thresholds = []
    for outer in folds:
        held = str(outer["validation_station"])
        train = data.loc[data.station.ne(held) & data.ice.notna()].copy()
        valid = data.loc[data.station.eq(held)].copy()
        if set(train.station) != set(outer["training_stations"]):
            raise AssertionError("Outer training stations differ from frozen split")
        if train.station.eq(held).any() or valid.empty:
            raise AssertionError("Held-out station leakage or missing validation")
        if args.smoke:
            train = smoke_sample(train)
        y_oof, score_oof = inner_oof(train, outer["inner_folds"], features)
        threshold, inner_f1 = choose_threshold(y_oof, score_oof)
        model = make_model()
        model.fit(train[features], train.ice.astype(int))
        score = model.decision_function(valid[features])
        valid["model_score"] = score
        valid["predicted_ice"] = (score >= threshold).astype(int)
        valid["threshold"] = threshold
        outputs.append(valid[["station", "route", "time", "ice", "state_raw",
                              "model_score", "predicted_ice", "threshold"]])
        thresholds.append({"held_out_station": held, "threshold": threshold,
                           "inner_oof_slot_f1": inner_f1,
                           "inner_train_rows": len(train),
                           "inner_positive_slots": int(train.ice.eq(1).sum()),
                           "validation_rows": len(valid),
                           "validation_positive_slots": int(valid.ice.eq(1).sum())})
        print(f"LOSO {held}: inner threshold {threshold:.3f}; "
              f"validation positives {int(valid.ice.eq(1).sum())}", flush=True)
    prediction = pd.concat(outputs, ignore_index=True)
    if prediction.duplicated(["station", "time"]).any():
        raise AssertionError("Duplicate OOF prediction")
    valid_prediction = prediction.loc[prediction.ice.notna()].copy()
    if not args.smoke:
        audit = json.loads((private / "development" / "eda_summary.json").read_text(encoding="utf-8"))
        if (len(prediction) != audit["rows"]
                or len(valid_prediction) != audit["valid_label"]
                or int(valid_prediction.ice.sum()) != audit["ice_slots"]):
            raise AssertionError("OOF rows or Ice labels differ from data audit")

    records = [(str(row.station), row.time,
                int(row.ice) if pd.notna(row.ice) else None,
                int(row.predicted_ice)) for row in prediction.itertuples(index=False)]
    daily = daily_scores(records, unit="10_minute_observations",
                         expected_slots=144, minimum_coverage=1.0)
    daily_any = daily_scores(records, unit="any_ice_per_day",
                             expected_slots=144, minimum_coverage=1.0)
    route_map = prediction.groupby("station").route.first().to_dict()
    station_rows = []
    for station, part in prediction.groupby("station"):
        pairs = part.loc[part.ice.notna()]
        micro = binary_metrics(pairs.ice.astype(int), pairs.predicted_ice.astype(int))
        station_daily = [row for row in daily if row["station"] == station]
        average = macro_scores(station_daily, station_first=False)
        station_rows.append({"station": station, "route": route_map[station],
                             "target_slots": len(part), "valid_label_slots": len(pairs),
                             "ice_slots": int(pairs.ice.sum()),
                             "predicted_ice_slots": int(pairs.predicted_ice.sum()),
                             "slot_tp": micro["tp"], "slot_fp": micro["fp"],
                             "slot_fn": micro["fn"], "slot_precision": micro["precision"],
                             "slot_recall": micro["recall"], "slot_f1": micro["f1"],
                             "daily_accepted_days": average["accepted_days"],
                             "daily_defined_f1_days": average["defined_f1_days"],
                             "daily_f1": average["f1"],
                             "daily_precision": average["precision"],
                             "daily_recall": average["recall"]})
    station_table = pd.DataFrame(station_rows)
    slot_micro = binary_metrics(valid_prediction.ice.astype(int),
                                valid_prediction.predicted_ice.astype(int))
    source_config = json.loads((ROOT / "config/data_source.json").read_text(encoding="utf-8"))
    summary = {
        "data_release": source_config["release"], "archive_sha256": source_config["sha256"],
        "status": "provisional_development_only_ice_baseline",
        "aws_variant": args.variant,
        "validation": "outer LOSO; threshold from inner station-OOF pooled slot F1",
        "score_semantics": "class-weighted logistic decision score, not calibrated probability",
        "feature_set": features,
        "classifier": "median imputation+missing indicators+scaling+balanced logistic C=0.1",
        "smoke": args.smoke, "stations": len(station_table),
        "target_slots": len(prediction), "valid_label_slots": len(valid_prediction),
        "ice_slots": int(valid_prediction.ice.sum()),
        "slot_micro": slot_micro,
        "daily_10minute_station_macro": macro_scores(daily, station_first=True),
        "daily_10minute_day_macro": macro_scores(daily, station_first=False),
        "daily_10minute_route_macro": route_macro_scores(daily, route_map),
        "daily_anyice_station_macro_candidate": macro_scores(daily_any, station_first=True),
        "daily_definition": "provisional: 144 fully paired KST slots required; undefined metrics kept null",
        "python": platform.python_version(), "sklearn": sklearn.__version__,
    }
    output_name = {
        "nearest": "ice_logistic", "fallback": "ice_fallback_logistic",
        "history": "ice_history_logistic",
        "fog": "ice_fog_logistic",
    }[args.variant]
    if args.smoke:
        output_name = "smoke_" + output_name
    out = private / output_name
    out.mkdir(parents=True, exist_ok=True)
    prediction.to_parquet(out / "predictions.parquet", index=False, compression="zstd")
    prediction[["station", "route", "time", "ice", "model_score", "predicted_ice",
                "threshold"]].to_csv(out / "10min_predictions.csv", index=False,
                                      encoding="utf-8-sig")
    pd.DataFrame(daily).to_csv(out / "daily_10min_metrics.csv", index=False,
                               encoding="utf-8-sig")
    pd.DataFrame(daily_any).to_csv(out / "daily_anyice_candidate.csv", index=False,
                                   encoding="utf-8-sig")
    station_table.to_csv(out / "station_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(thresholds).to_csv(out / "thresholds.csv", index=False,
                                    encoding="utf-8-sig")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps({"output": str(out), **summary}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
