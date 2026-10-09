"""하루 전체 점수가 확보된 뒤 적용하는 사후 판정 후보. 실시간 경보용이 아니다."""
import numpy as np
import pandas as pd


def capped_daily_scores(frame, scores, top_k):
    if not isinstance(top_k, (int, np.integer)) or top_k < 1:
        raise ValueError("Positive integer daily cap required")
    scores = np.asarray(scores, float)
    if len(frame) != len(scores) or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
        raise ValueError("Finite classifier scores in [0,1] required")
    time = pd.to_datetime(frame.time)
    if time.dt.tz is not None:
        time = time.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
    work = pd.DataFrame({"station": frame.station.astype(str).to_numpy(), "time": time.to_numpy(), "score": scores, "order": np.arange(len(frame))})
    if work.duplicated(["station", "time"]).any():
        raise ValueError("Duplicate station/time")
    work["day"] = work.time.dt.normalize()
    ordered = work.sort_values(["station", "day", "score", "time"], ascending=[True, True, False, True])
    rank = ordered.groupby(["station", "day"]).cumcount().to_numpy()
    result = np.full(len(frame), -1.)
    kept = ordered.loc[rank < top_k]
    result[kept.order.to_numpy()] = kept.score.to_numpy()
    return result
