"""Deterministic trend signals and quality assessment for monthly Pageviews."""

import math
import statistics
from datetime import date


MIN_MONTHS = 12
FULL_MONTHS = 24
MIN_HALF = 6
SIGNIFICANT_PCT = 15.0
NEAR_ZERO_PCT = 5.0
LOW_VOLUME = 100.0
SPIKE_SHARE = 0.25
SEASONAL_CORRELATION = 0.65
SEASONAL_SWING = 0.5


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _classification(value: float | None) -> str:
    if value is None:
        return "unavailable"
    if value >= SIGNIFICANT_PCT:
        return "up"
    if value <= -SIGNIFICANT_PCT:
        return "down"
    if abs(value) <= NEAR_ZERO_PCT:
        return "flat"
    return "weak"


def _agreement(period_pct: float | None, trend_pct: float | None) -> str:
    first, second = _classification(period_pct), _classification(trend_pct)
    if first == second == "up":
        return "sustained_growth"
    if first == second == "down":
        return "sustained_decline"
    if first == second == "flat":
        return "no_convincing_change"
    return "uncertain"


def _theil_sen_percent(values: list[int | None], excluded: set[int]) -> float | None:
    observations = [(index, math.log1p(value)) for index, value in enumerate(values)
                    if value is not None and index not in excluded]
    if len(observations) < MIN_MONTHS:
        return None
    slopes = [(right_y - left_y) / (right_x - left_x)
              for i, (left_x, left_y) in enumerate(observations)
              for right_x, right_y in observations[i + 1:]]
    if not slopes:
        return None
    span = len(values) - 1
    return 100.0 * math.expm1(statistics.median(slopes) * span)


def _seasonality(values: list[int]) -> bool:
    if len(values) < FULL_MONTHS:
        return False
    previous, current = values[-24:-12], values[-12:]
    if not min(statistics.mean(previous), statistics.mean(current)):
        return False
    normalized = [[value / statistics.mean(year) for value in year]
                  for year in (previous, current)]
    detrended = []
    for year in normalized:
        slope = sum((index - 5.5) * (value - statistics.mean(year))
                    for index, value in enumerate(year)) / 143.0
        detrended.append([value - slope * (index - 5.5)
                          for index, value in enumerate(year)])
    if any(max(year) - min(year) < SEASONAL_SWING for year in detrended):
        return False
    left, right = detrended
    left_centered = [value - statistics.mean(left) for value in left]
    right_centered = [value - statistics.mean(right) for value in right]
    denominator = math.sqrt(sum(value * value for value in left_centered)
                            * sum(value * value for value in right_centered))
    return bool(denominator and sum(a * b for a, b in zip(left_centered, right_centered))
                / denominator >= SEASONAL_CORRELATION)


def _window(points: list[dict]) -> list[dict]:
    completed = [point for point in points if point["complete"]]
    return completed[-FULL_MONTHS:]


def _metrics(points: list[dict], excluded_date: str | None = None) -> dict:
    selected = _window(points)
    values = [point["views"] for point in selected]
    n = len(values)
    excluded = {index for index, point in enumerate(selected) if point["date"] == excluded_date}
    if excluded_date is not None and not excluded:
        raise ValueError(f"Excluded peak {excluded_date} is outside the analyzed completed months")
    if excluded and any(values[index] is None for index in excluded):
        raise ValueError("Cannot exclude a missing point as a peak")
    half = min(12, n // 2) if n >= MIN_MONTHS else 0
    comparison = selected[-2 * half:] if half else []
    previous = comparison[:half]
    current = comparison[half:]
    paired_index = next((index for index, point in enumerate(comparison) if point["date"] == excluded_date), None)
    if excluded_date is not None and paired_index is None:
        raise ValueError("Excluded peak must be within the equal-period comparison window")
    paired_date = None
    if paired_index is not None:
        counterpart_index = paired_index + half if paired_index < half else paired_index - half
        paired_date = comparison[counterpart_index]["date"]
        previous = [point for point in previous if point["date"] not in {excluded_date, paired_date}]
        current = [point for point in current if point["date"] not in {excluded_date, paired_date}]

    comparison_available = bool(half and len(previous) >= MIN_HALF and len(current) >= MIN_HALF
                                and all(point["views"] is not None for point in previous + current))
    previous_sum = sum(point["views"] for point in previous) if comparison_available else None
    current_sum = sum(point["views"] for point in current) if comparison_available else None
    period_pct = (100.0 * (current_sum / previous_sum - 1.0)
                  if previous_sum is not None and previous_sum > 0 else None)
    complete_values = [value for index, value in enumerate(values)
                       if value is not None and index not in excluded]
    trend_pct = (_theil_sen_percent(values, excluded)
                 if n >= MIN_MONTHS and all(value is not None for value in values) else None)
    mean_views = statistics.mean(complete_values) if complete_values else None
    median_views = statistics.median(complete_values) if complete_values else None
    cv = (statistics.pstdev(complete_values) / mean_views
          if mean_views and len(complete_values) >= 2 else None)
    peak = max(complete_values) if complete_values else None
    total = sum(complete_values)
    top_three = sum(sorted(complete_values, reverse=True)[:3]) if complete_values else None
    mad = (statistics.median(abs(value - median_views) for value in complete_values)
           if complete_values else None)
    peak_share = peak / total if total else None
    strong_spike = bool(peak is not None and median_views is not None and mad is not None
                        and peak_share is not None and peak_share >= SPIKE_SHARE
                        and peak >= 3 * max(median_views, 1)
                        and peak >= median_views + 4 * max(mad, 1))
    seasonality = bool(all(value is not None for value in values)
                       and _seasonality(values))
    return {
        "analysis_start": selected[0]["date"] if selected else None,
        "analysis_end": selected[-1]["date"] if selected else None,
        "completed_months": n,
        "comparison": {
            "months_per_period": len(previous) if comparison_available else None,
            "previous_start": previous[0]["date"] if previous else None,
            "previous_end": previous[-1]["date"] if previous else None,
            "current_start": current[0]["date"] if current else None,
            "current_end": current[-1]["date"] if current else None,
            "previous_views": previous_sum,
            "previous_mean_monthly_views": _rounded(previous_sum / len(previous)) if previous_sum is not None else None,
            "current_views": current_sum,
            "absolute_change": current_sum - previous_sum if comparison_available else None,
            "percent_change": _rounded(period_pct),
            "zero_baseline": previous_sum == 0 if previous_sum is not None else False,
            "paired_excluded_date": paired_date,
            "classification": _classification(period_pct),
        },
        "robust_trend": {
            "method": "theil_sen_log1p",
            "months": n - len(excluded),
            "span_months": max(n - 1, 0),
            "percent_change_over_span": _rounded(trend_pct),
            "classification": _classification(trend_pct),
        },
        "level_and_variability": {
            "mean_monthly_views": _rounded(mean_views),
            "median_monthly_views": _rounded(median_views),
            "coefficient_of_variation": _rounded(cv),
            "largest_month_views": peak,
            "largest_month_share": _rounded(100 * peak_share) if peak_share is not None else None,
            "top_three_share": _rounded(100 * top_three / total) if total else None,
        },
        "agreement": _agreement(period_pct, trend_pct),
        "diagnostics": {"strong_spike": strong_spike, "possible_seasonality": seasonality},
    }


def _flags(series: dict, metrics: dict, excluded_date: str | None) -> list[str]:
    flags = set(series.get("quality_flags", []))
    points = series["points"]
    flags.discard("missing_points")
    if any(point["missing"] and point["complete"] for point in points):
        flags.add("missing_points")
    if any(not point["complete"] for point in points):
        flags.add("incomplete_period")
    if metrics["completed_months"] < MIN_MONTHS:
        flags.add("too_few_points")
    elif metrics["completed_months"] < FULL_MONTHS:
        flags.add("short_history")
    if metrics["comparison"]["zero_baseline"]:
        flags.add("zero_baseline")
    previous_views = metrics["comparison"]["previous_views"]
    months_per_period = metrics["comparison"]["months_per_period"]
    if (previous_views is not None and months_per_period
            and previous_views / months_per_period < LOW_VOLUME):
        flags.add("low_volume")
    if metrics["diagnostics"]["strong_spike"]:
        flags.add("strong_spike")
    if metrics["diagnostics"]["possible_seasonality"]:
        flags.add("possible_seasonality")
    if "semantic_equivalence_warning" in flags:
        flags.add("doubtful_page_match")
    if excluded_date:
        flags.add("excluded_peak")
    return sorted(flags)


def _reliability(metrics: dict, flags: list[str]) -> dict:
    reasons = []
    if metrics["agreement"] == "uncertain":
        reasons.append("the two trend signals disagree or one is unavailable")
    if "too_few_points" in flags:
        reasons.append("fewer than 12 completed months")
    if "missing_points" in flags:
        reasons.append("missing monthly observations")
    if "zero_baseline" in flags:
        reasons.append("the previous period has zero views")
    if "low_volume" in flags:
        reasons.append("previous-period mean monthly views are below 100")
    if "doubtful_page_match" in flags:
        reasons.append("article equivalence is uncertain")
    if "strong_spike" in flags:
        reasons.append("one month contributes a large share")
    if "possible_seasonality" in flags:
        reasons.append("a repeated yearly pattern may affect the comparison")
    if "short_history" in flags:
        reasons.append("fewer than 24 completed months")
    if "incomplete_period" in flags:
        reasons.append("an incomplete period was excluded")
    if "page_redirect_or_title_change_possible" in flags or "api_article_title_differs" in flags:
        reasons.append("article title history may split views")
    severe = {"too_few_points", "missing_points", "zero_baseline", "low_volume", "doubtful_page_match"}
    if metrics["agreement"] == "uncertain" or severe.intersection(flags):
        level = "низька"
    elif reasons:
        level = "середня"
    else:
        level = "вища"
        reasons.append("signals agree across at least 24 complete months without quality warnings")
    return {"level": level, "reasons": reasons}


def _criterion(metrics: dict, criterion: dict | None) -> dict | None:
    if criterion is None:
        return None
    allowed = {"min_monthly_views", "min_period_change_pct"}
    if not criterion or set(criterion) - allowed:
        raise ValueError("Criterion must contain min_monthly_views and/or min_period_change_pct only")
    checks = {}
    values = {"min_monthly_views": metrics["level_and_variability"]["mean_monthly_views"],
              "min_period_change_pct": metrics["comparison"]["percent_change"]}
    for key, threshold in criterion.items():
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not math.isfinite(threshold):
            raise ValueError(f"Invalid criterion threshold: {key}")
        if key == "min_monthly_views" and threshold < 0:
            raise ValueError("min_monthly_views cannot be negative")
        actual = values[key]
        checks[key] = {"actual": actual, "minimum": threshold,
                       "met": None if actual is None else actual >= threshold}
    states = [check["met"] for check in checks.values()]
    status = "not_met" if False in states else "unknown" if None in states else "met"
    return {"status": status, "checks": checks}


def _analyze_one(series: dict, criterion: dict | None, excluded_date: str | None = None) -> dict:
    metrics = _metrics(series["points"], excluded_date)
    flags = _flags(series, metrics, excluded_date)
    return {"language": series["language"], "project": series["project"],
            "title": series["title"], "url": series["url"],
            "access": series["access"], "agent": series["agent"],
            "granularity": series["granularity"],
            "requested_start": series["requested_start"], "requested_end": series["requested_end"],
            "metrics": metrics, "quality_flags": flags,
            "reliability": _reliability(metrics, flags),
            "criterion_evaluation": _criterion(metrics, criterion),
            "sources": series["sources"]}


def analyze_trend(fetched: dict, *, criterion: dict | None = None,
                  exclusions: dict[str, dict] | None = None) -> dict:
    """Analyze fetched monthly series; alternatives never overwrite the baseline."""
    if fetched.get("status") not in {"ok", "partial"} or not fetched.get("series"):
        raise ValueError("Input must be a Pageviews series JSON with status ok or partial")
    series = fetched["series"]
    if any(row.get("granularity") != "monthly" for row in series):
        raise ValueError("Trend analysis requires monthly Pageviews; daily data is for peak inspection")
    definitions = {(row["access"], row["agent"], row["granularity"]) for row in series}
    if len(definitions) != 1:
        raise ValueError("All series must use the same access, agent, and granularity")
    languages = [row["language"] for row in series]
    if len(languages) != len(set(languages)):
        raise ValueError("Duplicate language series")
    expected_dates = None
    for row in series:
        dates = []
        seen_incomplete = False
        for point in row["points"]:
            day = date.fromisoformat(point["date"])
            views = point["views"]
            if day.day != 1 or (views is not None and
                                (not isinstance(views, int) or isinstance(views, bool) or views < 0)):
                raise ValueError("Invalid monthly point")
            if point["missing"] != (views is None) or not isinstance(point["complete"], bool):
                raise ValueError("Inconsistent monthly point")
            if not point["complete"]:
                seen_incomplete = True
            elif seen_incomplete:
                raise ValueError("Incomplete months must be trailing")
            dates.append(day)
        if not dates or dates != sorted(set(dates)):
            raise ValueError("Monthly points must have unique ascending dates")
        if any((left.year * 12 + left.month + 1) != (right.year * 12 + right.month)
               for left, right in zip(dates, dates[1:])):
            raise ValueError("Monthly points must be contiguous")
        if expected_dates is None:
            expected_dates = dates
        elif dates != expected_dates:
            raise ValueError("All language series must cover the same months")
    exclusions = exclusions or {}
    if set(exclusions) - set(languages):
        raise ValueError("Peak exclusion language is absent from series")
    analyses = [_analyze_one(row, criterion) for row in series]
    alternatives = []
    for row in series:
        if row["language"] not in exclusions:
            continue
        exclusion = exclusions[row["language"]]
        peak_date, reason = exclusion.get("date"), exclusion.get("reason", "").strip()
        if not reason:
            raise ValueError("Peak exclusion requires a reason")
        try:
            day = date.fromisoformat(peak_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("Peak exclusion date must be YYYY-MM-DD") from exc
        if day.day != 1:
            raise ValueError("Monthly peak exclusion date must be the first of a month")
        alternate = _analyze_one(row, criterion, peak_date)
        baseline = next(item for item in analyses if item["language"] == row["language"])
        alternatives.append({"language": row["language"], "excluded_date": peak_date,
                             "reason": reason, "analysis": alternate,
                             "original_agreement": baseline["metrics"]["agreement"],
                             "alternative_agreement": alternate["metrics"]["agreement"],
                             "conclusion_changed": baseline["metrics"]["agreement"] != alternate["metrics"]["agreement"]})
    return {
        "status": "analyzed",
        "request": fetched["request"],
        "resolved_pages": fetched["resolved_pages"],
        "series": series,
        "metrics": analyses,
        "language_comparison": {
            "basis": "same_metric_definition_and_months",
            "dynamics": [{"language": item["language"],
                          "period_change_pct": item["metrics"]["comparison"]["percent_change"],
                          "robust_trend_pct": item["metrics"]["robust_trend"]["percent_change_over_span"],
                          "agreement": item["metrics"]["agreement"]}
                         for item in analyses],
            "scale": [{"language": item["language"],
                       "mean_monthly_views": item["metrics"]["level_and_variability"]["mean_monthly_views"]}
                      for item in analyses],
            "interpretation": "Compare dynamics separately from absolute views; neither ranks paying markets.",
        },
        "alternatives": alternatives,
        "criterion": criterion,
        "method": {"minimum_months": MIN_MONTHS, "full_window_months": FULL_MONTHS,
                   "minimum_months_per_period": MIN_HALF,
                   "significant_change_pct": SIGNIFICANT_PCT,
                   "near_zero_pct": NEAR_ZERO_PCT,
                   "low_monthly_views": LOW_VOLUME,
                   "spike_share_threshold": SPIKE_SHARE,
                   "spike_median_multiple": 3,
                   "spike_mad_multiple": 4,
                   "seasonal_correlation_threshold": SEASONAL_CORRELATION,
                   "seasonal_swing_threshold": SEASONAL_SWING},
        "quality_flags": sorted({flag for item in analyses for flag in item["quality_flags"]}),
        "assumptions": ["One article per language is a proxy for topic interest, not full topic coverage.",
                        "Language edition is not audience geography or market demand.",
                        *[f"Excluded {item['language']} peak {item['excluded_date']}: {item['reason']}; "
                          f"paired month {item['analysis']['metrics']['comparison']['paired_excluded_date']}."
                          for item in alternatives]],
        "sources": fetched["sources"],
        "cache": fetched.get("cache"),
    }
