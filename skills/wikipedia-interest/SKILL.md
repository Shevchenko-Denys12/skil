---
name: wikipedia-interest
description: Resolve Wikipedia articles across language editions, fetch cached Pageviews, analyze trends, and create a chart and one-page PDF. Use when a user asks how interest in a topic changed on Wikipedia.
---

# Wikipedia interest

**The full workflow is available:** the skill verifies articles, fetches and caches Pageviews, calculates deterministic trend signals with quality flags, and creates a PNG chart and one-page PDF. Use the analyzed JSON for any statement about direction. The chart and PDF consume this same JSON and do not recalculate the trend. The validation status and unresolved live examples are recorded in [references/stage-6-validation.md](references/stage-6-validation.md).

## Set up the interpreter

Run from this skill directory. All CLI entry points import chart and PDF dependencies, so use the installed virtual environment for **every** command, including `resolve` and `fetch`. If it is not already installed:

```sh
python3 -m venv /tmp/wikipedia-interest-venv
/tmp/wikipedia-interest-venv/bin/python -m pip install -r requirements.txt
```

Check `/tmp/wikipedia-interest-venv/bin/python -c 'import PIL, reportlab, pypdfium2'` before the workflow. If network installation is unavailable, use an existing environment with these packages or report the dependency block; do not guess from a failed system-Python invocation.

Each command prints full JSON to stdout as well as writing `--output`. For a multi-year run, redirect stdout to a temporary log or `/dev/null` after supplying `--output`; then inspect only the saved fields needed for the answer. Do not paste the full monthly `series` into the agent context. Keep stderr visible so tool failures are not missed.

## One-command workflow

For a straightforward request with a topic, target languages, and dates, call the thin orchestrator. It returns compact JSON and saves every artifact outside this skill directory:

```sh
/tmp/wikipedia-interest-venv/bin/python scripts/run.py --topic 'Астрономія' --languages uk --start 2023-01-01 --end 2024-12-31 --contact 'you@example.org' --cache-dir /tmp/wikipedia-interest-cache --artifact-dir /tmp/wikipedia-interest-artifacts/astronomy
```

If article resolution returns `needs_confirmation`, stop: report the proposed titles and warnings and request a user-provided `--page LANGUAGE=TITLE_OR_URL`; there is no chart or PDF. If it returns `complete`, use `metrics` and `artifacts` for the answer. A saved verified selection can be reused with `--resolved /path/to/resolved_pages.json` in place of `--topic` and `--languages`. Each `run.py` invocation requires an artifact directory without existing workflow outputs, including retries after an unresolved or failed run. Choose a new `--artifact-dir` and reuse the cache or saved resolution; existing outputs are preserved. For thresholds or an alternative peak, pass `--criterion-json` or `--exclude-peak` as described below. The independent tools remain available for rerunning only a changed step. See [EVALUATOR.md](EVALUATOR.md) for the complete launch and expected output.

## Resolve a topic

Ask for target language codes and a topic or explicit article names/URLs. Run from this skill directory:

```sh
/tmp/wikipedia-interest-venv/bin/python scripts/resolve_topic.py --topic 'Astronomy' --languages uk --contact 'you@example.org' --output /tmp/wikipedia-interest-artifacts/resolved_pages.json
```

Replace `you@example.org` with a real contact email or HTTPS contact URL. Wikimedia requests require an identifying `User-Agent`. `--output` is optional; JSON always prints to stdout. Output files must be outside the skill source directory.

For an explicit article or a correction, add `--page 'uk=Астрономія'` or `--page 'uk=https://uk.wikipedia.org/wiki/Астрономія'`. Repeat `--page` for multiple languages. A topic can be omitted when at least one explicit page is given. `--languages` is required and all overrides must name one of those languages.

The result has `status: "resolved"` only when every requested language has a selected article. Otherwise it has `status: "needs_confirmation"` and per-language `status`, warnings, and any candidates. Show the titles and URLs to the user. If a page is missing, a topic is broad, or a disambiguation page appears, ask for a more specific article or use a user-provided override. An explicit override is selected but a semantic mismatch with another page's interlanguage link remains visible as a warning. One article does not fully represent a broad topic. The [three example checks](references/demo-resolutions.md) show resolved and unresolved cases.

## Fetch Pageviews

Only pass a `resolved` JSON file whose top-level status is `resolved`. The command requires an explicit date range, cache directory, and contact:

```sh
/tmp/wikipedia-interest-venv/bin/python scripts/fetch_pageviews.py --resolved /tmp/wikipedia-interest-artifacts/resolved_pages.json --start 2024-01-01 --end 2024-12-31 --granularity monthly --access all-access --agent user --cache-dir /tmp/wikipedia-interest-cache --contact 'you@example.org' --output /tmp/wikipedia-interest-artifacts/series.json
```

Replace the contact with a real email or HTTPS URL. Defaults are `monthly`, `all-access`, and `user`. `daily` is available for short periods or peak inspection; trend analysis uses monthly points. Both the cache and output must be outside the skill directory. The command prints JSON and optionally saves it. Read [references/cache-and-series.md](references/cache-and-series.md) when interpreting points, cache behavior, or quality flags. Missing points have `views: null`; incomplete current periods are flagged and excluded from analysis.

## Analyze the monthly series

```sh
/tmp/wikipedia-interest-venv/bin/python scripts/analyze_trend.py --series /tmp/wikipedia-interest-artifacts/series.json --output /tmp/wikipedia-interest-artifacts/analysis.json
```

Read [references/methodology.md](references/methodology.md) before interpreting the two signals, reliability, or exclusions. The output separately gives equal-period percentage change, robust trend percentage, their agreement, quality flags, and practical reliability. An `uncertain` agreement cannot support a confident recommendation. Compare language dynamics separately from absolute view counts. Explain selected article titles, date range, source URLs, assumptions, and limitations; suggest a next hypothesis check rather than a claim of demand.

Optional thresholds go in a JSON file such as `{"min_monthly_views": 100, "min_period_change_pct": 15}` and are passed with `--criterion-json /tmp/criterion.json`. They are evaluated after trend calculation. To inspect a peak, add `--exclude-peak 'uk=2024-09-01:reason for exclusion'`; the original and alternative results both remain in the output. Do not exclude an event without stating the reason.

## Create the chart and PDF

```sh
/tmp/wikipedia-interest-venv/bin/python scripts/plot.py --analysis /tmp/wikipedia-interest-artifacts/analysis.json --output /tmp/wikipedia-interest-artifacts/chart.png --language uk
/tmp/wikipedia-interest-venv/bin/python scripts/report.py --analysis /tmp/wikipedia-interest-artifacts/analysis.json --chart /tmp/wikipedia-interest-artifacts/chart.png --output /tmp/wikipedia-interest-artifacts/report.pdf --language uk
```

`report.py` refreshes the PNG from the same analyzed JSON before embedding it. Both outputs must be outside the skill source tree. `--language en` changes report and chart labels; article titles and source data remain as returned by Wikipedia. The PDF contains the requested range, equal-period comparison and robust trend separately, the agreement, source URLs, reliability reasons, limitations, and a next validation action. If many long source URLs cannot fit legibly on one page, the command reports an error instead of omitting them. The full route and interchange fields are in [references/contract.md](references/contract.md). Read [references/wikimedia-api.md](references/wikimedia-api.md) when changing API access. For setup, see [README.md](README.md).

## Respond to the user

Present **facts first**: name each selected article and URL, language edition, dates, metric definition, equal-period change, robust trend, agreement, and reliability. Explain how articles were selected (`match_method`) and expose warnings or unresolved matches. Cite the exact numbers in the analyzed JSON; do not invent precision or add a number absent from it. If a peak was excluded, state the reason and compare the original and alternative values and conclusion.

Copy every public link **verbatim** from `resolved_pages[].url` or `metrics[].sources` in the saved JSON. API data often comes from multiple year-specific URLs. Never construct a combined URL, manually encode a title, or link to a date range that is absent from `sources`. Check each answer link against those fields before responding.
For local artifacts, use the absolute paths returned by `plot.py` and `report.py`; write Markdown links as `[label](/absolute/path)` without a space after `(`.

Then give a clearly marked **interpretation** of article attention. State the assumptions and quality limits, especially missing or incomplete months, possible seasonality, sparse views, and uncertain article equivalence. Do not infer causality, audience geography, market size, or willingness to pay from Pageviews. Suggest which language audiences to investigate next only when the signals and reliability support it; otherwise suggest a narrower follow-up. End with a concrete next hypothesis check, such as interviews or a landing-page test, rather than promising product demand. Link the chart, PDF, and primary source URLs.

Always distinguish facts from interpretation. Pageviews are a signal of attention to an article, not evidence of product demand, geography, or willingness to pay.
