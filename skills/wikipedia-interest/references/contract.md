# JSON and artifact contract

The skill implements article resolution, Pageviews fetching, deterministic `metrics`, quality flags, assumptions, optional criteria, excluded-peak alternatives, and PNG/PDF artifacts. No metric is fabricated when a step fails.

`analyze_trend.py` consumes the Stage 3 series JSON and returns `status: "analyzed"`, the original `series`, `metrics` (one record per language), `language_comparison`, `alternatives`, `method`, `quality_flags`, `assumptions`, `sources`, and cache provenance. Each metric record has an equal-period `comparison`, `robust_trend`, `agreement`, level and variability figures, reliability with reasons, and optional `criterion_evaluation`. Read [methodology.md](methodology.md) for exact formulas and thresholds.

The resolver emits one object per requested language in `resolved_pages`. Each has `language`, `project`, `status` (`selected`, `needs_confirmation`, or `missing`), canonical `title` and `url` when available, `match_method` (`user_page`, `exact_title`, `interlanguage_link`, `search_candidate`, or `none`), `warnings`, and `candidates`. `seed` records the article used for interlanguage links and whether its selection was confirmed by an exact title or explicit user page. `status: "resolved"` at the top level means all entries are `selected`; otherwise it is `needs_confirmation`. `sources` lists only API editions queried during resolution.

`plot.py` requires a Stage 4 object with `status: "analyzed"` and writes a PNG outside the skill tree. Its stdout JSON contains `chart`, `languages`, `marked_incomplete`, and `marked_excluded`. `report.py` requires the same object and writes a one-page PDF and regenerated PNG; its stdout JSON contains `pdf`, `chart`, `pages`, and `languages`. Chart and PDF values are presentation of the saved `metrics` and `series`, not a new calculation. Both commands reject raw fetched data.

`run.py` orchestrates those same stages. With a topic and language list it resolves fresh pages; with `--resolved` it reuses a saved verified selection. It writes `resolved_pages.json` first. When selection is unresolved, it returns `status: "needs_confirmation"`, `resolved_pages`, `next_action`, and only the resolved artifact path. On success it returns `status: "complete"`, compact per-language `metrics` with exact source URLs, `alternatives`, `assumptions`, `quality_flags`, cache counts, `pdf_pages`, and paths to all five artifacts. Outputs are outside the skill directory. The separate tools retain their original contracts.

| Field | Meaning |
| --- | --- |
| `request` | Topic or explicit articles, language codes, inclusive dates, and Pageviews metric definition. Presentation language is a CLI option. |
| `resolved_pages` | One selected canonical title, article URL, project, match method, and match warnings per language. |
| `series` | Timestamped views and completeness state for each article; preserve the metric definition (`project`, `access`, `agent`, `granularity`). Missing values remain missing. |
| `metrics` | Equal-length period change, robust trend, their agreement, scale, variability, and peak contribution, each with method details. |
| `quality_flags` | Ambiguity, missing data, incomplete periods, small samples, spikes, seasonality, and other confidence limits. |
| `assumptions` | Article equivalence and analyst or user choices, including any excluded peak and its reason. |
| `sources` | Article and API URLs plus retrieval dates and metric parameters. |
| `artifacts` | Paths to saved JSON, chart, and PDF outside the skill directory. |

Each result must identify the article title, language, project, requested and analyzed periods, granularity, and source. Pageviews signal attention to a page, not product demand or audience location. Follow-up analysis should reuse saved data when the cached metric definition and time range cover the request.

`run.py` refuses an artifact directory containing any of its five output paths before resolving or fetching. Choose a new directory for a retry or follow-up and reuse the cache or `--resolved`. This preserves previous results and prevents a stopped run from appearing to have produced an old PDF. Failures may leave partial outputs in the new directory; only `status: "complete"` confirms completion. Independent stage commands can still overwrite explicitly supplied output paths. Concurrent runs must use distinct artifact directories.
