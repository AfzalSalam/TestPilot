# ADR-003: Performance regression thresholds
**Status:** Accepted
**Context:** Response times are noisy; a fixed percentage threshold floods alerts for fast endpoints and misses slow ones.
**Decision:** Over the last 5 passing runs (min 3 samples), flag only if current > max(median×1.5, median + 3×1.4826×MAD, median + 100 ms). All thresholds are configurable.
**Consequences:** Few false positives; needs history, so new tests report `insufficient_data`. The thresholds are engineering judgement, not tuned on a benchmark corpus.
**Alternatives:** Mean/stddev (outlier-sensitive), percentile bands, fixed % only.
