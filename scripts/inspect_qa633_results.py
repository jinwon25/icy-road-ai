from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_method_blending import read


def main():
    out = ROOT / 'outputs/private/qa633_development_20261013_v1'; s = read(out / 'summary.json')
    for name in ['original', 'equal_distance_mse_mae300', 'equal_nohistory_pair', 'equal_trio_nohistory', 'equal_trio_memory', 'catboost400']:
        for minimum in ['144', '130', '72', '1']:
            r = s['reports'][name][minimum]
            print(name, minimum, {k: r[k] for k in ['coverage_days', 'excluded_ice_days', 'miss_only_days', 'precision_days', 'recall_days', 'f1_days', 'precision_available_station_mean', 'recall_available_station_mean', 'f1_available_station_mean', 'recall_all_population_station_mean']})
    print(pd.read_csv(out / 'wrong_intersection_comparison.csv').loc[lambda f: f.method.isin(['original', 'equal_nohistory_pair', 'equal_trio_nohistory'])].to_string(index=False))


if __name__ == '__main__': main()
