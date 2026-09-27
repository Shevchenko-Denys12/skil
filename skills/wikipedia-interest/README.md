# Wikipedia interest skill

The skill resolves Wikipedia articles, fetches cached per-article Pageviews, analyzes monthly trends, and creates a PNG chart and one-page PDF from the analyzed JSON.

For the shortest evaluator route, use [EVALUATOR.md](EVALUATOR.md): install dependencies once, then run `scripts/run.py` with a topic, languages, dates, contact, cache directory, and artifact directory. It saves all intermediate JSON plus the chart and PDF, and returns a compact machine-readable summary. It stops at `needs_confirmation` when article matching is unresolved. The separate commands below remain useful for follow-ups and inspection.

## Install and run

For each `run.py` invocation, choose an artifact directory without previous workflow outputs. The command rejects occupied output paths before doing work. Reuse the cache and optionally `--resolved` for follow-ups; existing reports are preserved. See [the project review](references/project-review.md) for verified limitations and optimization priorities.

Run from this directory with Python 3.11+. Install the pinned dependencies in `requirements.txt`. The virtual environment and output stay outside the skill directory.

```sh
python3 -m venv /tmp/wikipedia-interest-venv && /tmp/wikipedia-interest-venv/bin/python -m pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 /tmp/wikipedia-interest-venv/bin/python scripts/resolve_topic.py --topic 'Astronomy' --languages uk --contact 'you@example.org' --output /tmp/wikipedia-interest-artifacts/resolved_pages.json
```

Replace `you@example.org` with a real email address or HTTPS contact URL. Resolution uses the live Wikipedia Action API and needs network access. It prints JSON and optionally saves the same result at `--output`.

After checking that resolution returned `"status": "resolved"`, fetch a monthly series:

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/wikipedia-interest-venv/bin/python scripts/fetch_pageviews.py --resolved /tmp/wikipedia-interest-artifacts/resolved_pages.json --start 2024-01-01 --end 2024-12-31 --cache-dir /tmp/wikipedia-interest-cache --contact 'you@example.org' --output /tmp/wikipedia-interest-artifacts/series.json
```

The first request uses the live Wikimedia Analytics API. Repeating it or narrowing the dates can use cached historical data. The JSON includes points, metric parameters, source URLs, quality flags, and cache hit/miss counts. `--granularity daily` is available for short periods; `--access` and `--agent` change the metric definition. See [references/cache-and-series.md](references/cache-and-series.md).

Analyze a monthly series without another network request:

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/wikipedia-interest-venv/bin/python scripts/analyze_trend.py --series /tmp/wikipedia-interest-artifacts/series.json --output /tmp/wikipedia-interest-artifacts/analysis.json
```

To assess user thresholds, pass `--criterion-json /tmp/criterion.json` with an object such as `{"min_monthly_views": 100, "min_period_change_pct": 15}`. To compare an alternative excluding a documented peak, pass `--exclude-peak 'uk=2024-09-01:one-off event'`. The command preserves the original and alternative results; see [references/methodology.md](references/methodology.md) for formulas, boundaries, and interpretation.

Create a shareable chart and PDF from that same JSON without network access:

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/wikipedia-interest-venv/bin/python scripts/plot.py --analysis /tmp/wikipedia-interest-artifacts/analysis.json --output /tmp/wikipedia-interest-artifacts/chart.png --language uk
PYTHONDONTWRITEBYTECODE=1 /tmp/wikipedia-interest-venv/bin/python scripts/report.py --analysis /tmp/wikipedia-interest-artifacts/analysis.json --chart /tmp/wikipedia-interest-artifacts/chart.png --output /tmp/wikipedia-interest-artifacts/report.pdf --language uk
```

`report.py` regenerates the chart before embedding it, keeping the two artifacts in sync. The PDF is one A3 landscape page with the selected topic and period, chart, two trend signals, assessment, reliability explanation, assumptions, recommendation, and clickable article and API URLs. The Ukrainian glyphs use the bundled DejaVu Sans font; its license is in [assets/LICENSE](assets/LICENSE). `--language en` changes presentation labels. The report uses saved Stage 4 metrics and does not calculate new ones.

To verify explicit pages and override a match:

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/wikipedia-interest-venv/bin/python scripts/resolve_topic.py --languages uk en --page 'uk=Астрономія' --page 'en=https://en.wikipedia.org/wiki/Astronomy' --contact 'you@example.org'
```

The `doctor` command remains available:

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/wikipedia-interest-venv/bin/python scripts/cli.py doctor --cache-dir /tmp/wikipedia-interest-cache --artifact-dir /tmp/wikipedia-interest-artifacts
```

Both work directories must be distinct and outside the skill source tree. See [SKILL.md](SKILL.md) for how an agent should interpret matches and [references/contract.md](references/contract.md) for the JSON fields.

## Test

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/wikipedia-interest-venv/bin/python -m unittest discover -s tests -v
```

The offline suite includes three initial workflow fixtures, two follow-up checks, cache reuse, conclusion change after excluding a peak, and a one-page PDF assertion. The [Stage 6 validation log](references/stage-6-validation.md) records live Pageviews spot checks and the tool-using fast-model run, including its initial error and the corrected rerun. Fixture article links are synthetic; unresolved live topics still need user-confirmed pages.

Planned extensions are prioritized in [references/roadmap.md](references/roadmap.md). They are not mixed into the current single-article-per-language result.
