# Deterministic trend methodology (Stage 4)

This method describes article pageviews, not demand, market size, audience location, or willingness to pay. It accepts only monthly series with the same `access`, `agent`, `granularity`, and calendar months for every language. Daily series remain useful for inspecting a suspected peak, but are not analyzed as a monthly trend.

## Analysis window and two signals

Incomplete months are excluded. The most recent 24 completed monthly points form the analysis window; if fewer exist, use all completed points. Points must be consecutive in the input. A missing value stays `null` and is never replaced by zero or interpolated. If the analysis window contains any missing value, both signals are unavailable. Missing values outside the window remain a quality flag.

At least 12 completed months are required. With 24 or more, compare the latest 12 against the preceding 12. With 12–23, compare the latest two equal halves of length `floor(n/2)` (6–11 months); an extra oldest month is outside the equal-period comparison but remains in the robust trend window. The output gives both period boundaries and sums.

**Equal-period change:** `100 × (sum(current) / sum(previous) − 1)`. Also return both sums, their absolute difference, and the previous-period mean monthly views. When the previous sum is zero, return `percent_change: null`, `zero_baseline: true`, and an uncertain overall direction. Never describe zero-to-positive change as a precise percentage.

**Robust trend:** take `log(1 + views)` for each completed month and compute every pairwise slope `(log1p(v_j) − log1p(v_i)) / (j − i)`. The median slope is Theil–Sen. Convert it to change across the window with `100 × expm1(median_slope × (n − 1))`. The original month indices are retained when a peak is excluded. This reduces the influence of one extreme point; it does not prove causality or remove seasonality. The trend is unavailable with fewer than 12 non-excluded complete points or any missing value in the window.

All displayed percentages, means, coefficients, and shares are rounded to one decimal using Python's `round` (ties to even). Classification uses the **unrounded** signal values.

## Agreement rule

Each signal is `up` at ≥ +15%, `down` at ≤ −15%, `flat` within ±5%, and `weak` between those bands. The overall label is `sustained_growth` when both are `up`, `sustained_decline` when both are `down`, and `no_convincing_change` when both are `flat`. Every other combination, including an unavailable signal, is `uncertain`. A `weak` signal cannot support a confident direction. Thresholds appear in the JSON `method` object.

## Quality and practical reliability

The output reports mean and median monthly views, population coefficient of variation (`pstdev / mean`), largest-month views, largest-month share of the window total, and top-three-month share. Shares are `null` when the total is zero.

- `too_few_points`: fewer than 12 completed months. `short_history`: 12–23 completed months.
- `low_volume`: previous-period mean is under 100 views per month. `zero_baseline`: previous-period sum is zero.
- `missing_points`: at least one completed requested month is missing. `incomplete_period`: at least one requested month is unfinished; it is excluded from signals.
- `strong_spike`: the largest month contributes at least 25% of window views, has at least 3× the median, and is at least `median + 4 × max(MAD, 1)`. MAD is median absolute deviation. This is a diagnostic, not an automatic removal.
- `possible_seasonality`: at least two full years are available, the two latest 12-month profiles each have a detrended swing of at least 0.5 of their yearly mean, and their detrended monthly Pearson correlation is at least 0.65. Linear within-year drift is removed before correlation. This is a warning, not a formal seasonality test.
- `doubtful_page_match`: the resolver or fetcher reported uncertain semantic equivalence. Redirect and API-title warnings remain visible separately.

Reliability is a practical label, not a statistical confidence level. It is `низька` when the overall direction is `uncertain` or any of `too_few_points`, `missing_points`, `zero_baseline`, `low_volume`, or `doubtful_page_match` occurs. It is `середня` when the signals agree but there are other warnings, including a spike, seasonality, short history, an incomplete excluded month, or title-history uncertainty. It is `вища` only when signals agree over at least 24 complete months without warnings. The JSON includes the reasons.

## Criteria and excluded peaks

An optional criterion JSON supports `min_monthly_views` (mean over the analysis window) and `min_period_change_pct`. It is evaluated **after** trend computation against the displayed one-decimal metrics and never changes the signals or agreement. A missing metric yields `unknown`; any failed check yields `not_met`; all passed checks yield `met`.

`--exclude-peak LANGUAGE=YYYY-MM-01:REASON` keeps the original analysis and adds an alternative. The date must be a present, completed, non-missing month inside the equal-period comparison. The alternative removes that month from the robust trend and removes the same-position month from the other equal period for the equal-period comparison. This preserves equal observation counts. Both signals and quality diagnostics are recomputed; the JSON states the paired date, reason, original and alternative agreement, and whether the conclusion changed. If too few paired months remain, the period signal becomes unavailable and the alternative is uncertain.

Comparisons between languages list percentage dynamics separately from absolute monthly view level. They are **not** rankings of paid markets. Article choice, external events, seasonality, API gaps, and historical title changes can alter interpretation even when the formulas are deterministic.
