"""제공 DEM 원시값과 독립 DSM 미터 높이의 관계를 진단한다. 역변환을 적용하지 않는다."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, theilslopes

ROOT = Path(__file__).resolve().parents[1]


def main():
    private = ROOT / "outputs/private"
    native = pd.read_csv(private / "spatial/environment_features/segment_features.csv")
    external = pd.read_csv(private / "solar_terrain_features/segment_terrain.csv")
    pair = native[["seg_id", "dem_value"]].merge(external[["seg_id", "dsm_elevation_m"]], on="seg_id", validate="one_to_one").dropna()
    fit = theilslopes(pair.dsm_elevation_m, pair.dem_value)
    predicted = fit.slope * pair.dem_value + fit.intercept
    summary = {"status": "diagnostic_only_no_native_dem_rescaling", "paired_segments": len(pair),
               "spearman_rank_correlation": float(spearmanr(pair.dem_value, pair.dsm_elevation_m).statistic),
               "exploratory_robust_slope": float(fit.slope), "exploratory_intercept_m": float(fit.intercept),
               "exploratory_median_abs_residual_m": float(np.median(np.abs(predicted - pair.dsm_elevation_m))),
               "native_min": float(pair.dem_value.min()), "native_max": float(pair.dem_value.max()),
               "limitations": ["A fitted association does not establish the official scale/offset or vertical datum of the supplied DEM.",
                               "Copernicus is a separate DSM with different horizontal grid, vegetation/buildings and vintage.",
                               "Do not use the fitted slope/intercept as an inverse-normalization rule without source confirmation.",
                               "Copernicus-derived height features remain separate from supplied native DEM values."]}
    out = private / "spatial/environment_features"
    pair.to_csv(out / "independent_dem_pairs.csv", index=False, encoding="utf-8-sig")
    (out / "independent_dem_unit_audit.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
