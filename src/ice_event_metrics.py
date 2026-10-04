"""Exact ten-minute episode diagnostics, not official competition metrics."""
import pandas as pd


def event_metrics(frame, observed='ice', predicted='predicted_ice'):
    if frame.duplicated(['station', 'time']).any():
        raise ValueError('Duplicate station/time')
    totals = {'observed_events': 0, 'detected_events': 0,
              'predicted_events': 0, 'false_alarm_events': 0,
              'max_predicted_event_slots': 0}
    for _, group in frame.groupby('station'):
        group = group.sort_values('time').reset_index(drop=True)
        valid = group[observed].isin([0, 1]) & group[predicted].isin([0, 1])
        # Unknown observations break episodes rather than count as true negatives.
        contiguous = pd.to_datetime(group.time).diff().eq(pd.Timedelta(minutes=10))
        for column, count_key, match_key in ((observed, 'observed_events', 'detected_events'),
                                              (predicted, 'predicted_events', 'false_alarm_events')):
            active = valid & group[column].eq(1)
            starts = active & ~(active.shift(fill_value=False) & contiguous)
            episode_id = starts.cumsum()
            other = predicted if column == observed else observed
            for _, episode in group.loc[active].groupby(episode_id[active]):
                totals[count_key] += 1
                has_match = episode[other].eq(1).any()
                totals[match_key] += int(has_match if column == observed else not has_match)
                if column == predicted:
                    totals['max_predicted_event_slots'] = max(totals['max_predicted_event_slots'], len(episode))
    totals['event_recall'] = (totals['detected_events'] / totals['observed_events']
                              if totals['observed_events'] else None)
    return totals
