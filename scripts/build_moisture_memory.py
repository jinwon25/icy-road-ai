"""원천 AWS 이력을 한 번 생성하고 선택된 과거 관측 시각에 결합한다."""
import json
import sys
import zipfile
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_source import competition_archive, sha256_file
from src.moisture_memory import moisture_memory, MEMORY_FEATURES
from src.weather_features import _load_aws, _numeric_range
from src.validation import assert_training_stations


def main():
    private = ROOT / "outputs/private"
    path = private / "physical_features/features.parquet"
    data = pd.read_parquet(path)
    assert_training_stations(data.station.unique())
    archive = competition_archive(ROOT)
    with zipfile.ZipFile(archive) as z:
        aws = _load_aws(z, None)
    for c,low,high in [("air_temp",-60,70),("humidity",0,100),("rain_15m",0,500),("dewpoint",-80,60)]:
        _numeric_range(aws,c,low,high)
    history = moisture_memory(aws)
    renamed = history.rename(columns={"station":"aws_station", "source_time":"aws_source_time"})
    result = data.merge(renamed,on=["aws_station","aws_source_time"],how="left",validate="many_to_one")
    pd.testing.assert_frame_equal(data[["station","time","ice"]],result[["station","time","ice"]])
    good = result.aws_source_time.notna()
    if not (result.loc[good,"aws_source_time"] < result.loc[good,"time"]).all():
        raise AssertionError("Future AWS history")
    out=private/"moisture_memory";out.mkdir(parents=True,exist_ok=True)
    history.to_parquet(out/"aws_history.parquet",index=False,compression="zstd")
    result.to_parquet(out/"features.parquet",index=False,compression="zstd")
    summary={"rows":len(result),"ice_slots":int(result.ice.sum()),"features":MEMORY_FEATURES,
             "available":{c:int(result[c].notna().sum()) for c in MEMORY_FEATURES},
             "feature_input_sha256":sha256_file(path),"archive_sha256":sha256_file(archive),
             "semantics":["Rain15 windows overlap: maximum and observed wet fraction, never a summed rainfall volume.",
                          "Rolling windows are (source_time-hours,source_time]; source_time strictly precedes target.",
                          "Coverage counts use the expected ten-minute grid; unobserved periods are not imputed dry.",
                          "Last wet age is missing when no wet observation was found within72h.",
                          "These are residual-moisture proxies, not measured road water or ice storage."]}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary),flush=True)


if __name__ == "__main__": main()
