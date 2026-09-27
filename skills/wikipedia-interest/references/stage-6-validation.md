# Stage 6 validation log

Checked on 2026-09-27 (macOS, Python 3.14.7; supported minimum is 3.11). Run from the skill directory with the interpreter documented in `SKILL.md`:

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/wikipedia-interest-venv/bin/python -m unittest discover -s tests -v
```

## Deterministic tests and scenario fixtures

The offline suite tests article URL/title parsing, date normalization, API response shape, cache key and reuse, missing/incomplete buckets, two trend signals, zero baseline, seasonal and spike warnings, conflicting signals, and conclusion change after excluding a peak. `test_workflows.py` calls the real CLI entry point for `resolve`, `fetch`, `analyze`, `plot`, and `report` with Wikimedia-shaped API fixtures. Each scenario checks saved JSON, PDF text and one-page count. The two follow-ups check cache hits and no extra API fetch for a changed analysis.

| Natural-language scenario | Fixture check | Live-state qualification |
| --- | --- | --- |
| Intermittent fasting, Polish and Czech, 2023–2024 | Two-language pipeline reaches a PDF when the fixture supplies verified interlanguage pages. | The live resolver returned `needs_confirmation`: Czech `Přerušovaný půst` was selected, but no Polish page was verified. A real report must await a user-selected Polish page. |
| Astronomy, Ukrainian, 2023–2024 | Full pipeline reaches a PDF. | Live cached Pageviews and a real one-page PDF were also checked. |
| Learning English, Polish, Czech and Ukrainian | Three-language pipeline reaches a PDF when the fixture supplies explicit equivalent pages. | The live resolver returned `needs_confirmation` for all three on 2026-09-27 with seed `English as a second or foreign language`. The requested concept and article choices need confirmation before a real PDF. |
| Follow-up: add English to the astronomy comparison | Existing Ukrainian data has two cache hits; the two new English year chunks are fetched. | This is an offline fixture check, not a live English Pageviews comparison. |
| Follow-up: exclude December 2024 peak | Reuses saved series without API calls; baseline `uncertain` changes to `no_convincing_change` and the PDF says so. | This is a synthetic spike. The live astronomy September 2024 alternative retains `sustained_decline`. |

Fixture pages and counts are **synthetic** and validate the workflow, not actual article equivalence or real interest. The two unresolved live prompts cannot honestly produce a comparable report or PDF without the user's article choices.

## Raw Pageviews and rendered PDF audit

For the live Ukrainian `Астрономія` analysis, sampled raw API month counts matched the saved series exactly: 2023-01: 1,777; 2023-09: 9,857; 2024-01: 3,700; 2024-09: 4,687; 2024-12: 1,634. Summing the raw monthly counts gives 39,889 for 2023 and 25,473 for 2024, equal to the `comparison.previous_views` and `comparison.current_views` fields. The computed comparison is −36.1%, robust trend −44.3%, agreement `sustained_decline`, reliability `середня` due to possible seasonality. The generated PDF has one page; rendered inspection found readable Ukrainian glyphs, the same two percentages and conclusion, and a marked September 2024 excluded peak in the alternative report. ReportLab link annotations are present for article and Wikimedia API URLs.

## Fast-model tool run

The local Claude Code CLI (2.1.92) was attempted with `--model haiku`, a USD 0.10 cap and no tools for a simple probe. It returned repeated HTTP 400 errors with zero model tokens and zero reported cost, so it could not serve as the required model test. A separate Codex CLI run uses `gpt-6-luna`, a fast low-cost tool-capable model, in the skill directory with workspace-write sandbox and artifacts under `/tmp/wikipedia-interest-artifacts/`. The prompt asks for the live astronomy answer and PDF using the previously verified resolution and cached Pageviews. The tool event logs and final answer are saved alongside each run's artifacts.

Representative second-run prompt: “Follow SKILL.md to answer in Ukrainian: Ми думаємо додати курс з астрономії до освітнього застосунку. Чи зростав інтерес до цієї теми в україномовній Wikipedia за 2023–2024 роки, і наскільки висновку можна довіряти? Produce a chart and one-page PDF in `/tmp/wikipedia-interest-artifacts/luna-rerun`. The previously verified resolution is `/tmp/wikipedia-interest-artifacts/astronomy-resolved.json`; review and reuse it. Cache is `/tmp/wikipedia-interest-cache`. Contact: [project contact URL]. Do not edit source. Use tools and answer from saved JSON, with exact source links.” The first prompt had the same user question and inputs, without the final explicit exact-link reminder.

Reproduction requires a Codex account with access to `gpt-6-luna`, installed skill dependencies, the saved verified resolution, and the historical Pageviews cache (or live API access). The CLI shape used was:

```sh
codex exec -m gpt-6-luna -s workspace-write --skip-git-repo-check --ephemeral --json \
  -C /path/to/skills/wikipedia-interest \
  -o /tmp/wikipedia-interest-artifacts/luna-rerun/answer.md \
  'Follow SKILL.md to answer in Ukrainian: [astronomy user question and paths above]' \
  > /tmp/wikipedia-interest-artifacts/luna-rerun/events.jsonl
```

Actual skill tools in the first run: `fetch_pageviews.py`, `analyze_trend.py`, `plot.py`, `report.py`; the resolver result was checked and reused. The second run reused the existing analyzed JSON, then called `plot.py` and `report.py`. Both runs also used shell reads to inspect `SKILL.md`, JSON and method references. The second run used PDF rendering to inspect the report. The saved runs are `luna-run/events.jsonl` and `luna-rerun/events.jsonl`; `answer.md`, chart and PDF sit next to each log. These temporary logs are evidence for this workspace, not part of the installed skill.

The first Luna run read `SKILL.md`, inspected the verified article, called `fetch`, `analyze`, `plot`, and `report`, and produced a correct one-page PDF and numeric conclusion. It initially used system `python3`, which lacked Pillow, then attempted a package installation that failed because PyPI was unavailable inside its tool sandbox. It recovered by finding the existing virtual environment. Its final prose contained a **wrong, manually assembled Wikimedia API link**, despite correct metric numbers. `SKILL.md` was changed to name the required interpreter for every command, avoid flooding the model with full monthly JSON, and require exact URL strings copied from the saved JSON.

The second Luna run used that revised instruction. It selected the available virtual environment immediately, reused the saved analysis, created and rendered a one-page PDF, and included the exact two year-specific Pageviews URLs from `metrics[].sources` plus the exact article URL. A programmatic comparison of every HTTPS link in the answer with those JSON fields passed. It also included the alternative September 2024 calculation without changing the original conclusion. It initially tried unavailable Poppler commands and then used installed PDF libraries; the final PDF was rendered and inspected. The second answer has a minor Markdown spacing issue in its chart link, although the path itself exists.

The first run used 250,201 input tokens (231,424 cached) and 1,879 output tokens; the second used 257,248 input tokens (230,656 cached) and 2,726 output tokens. The event files span approximately 146 and 90 seconds respectively by filesystem timestamps. Monetary cost was not reported by the Codex CLI. These large context totals show that further tool-output reduction is still useful even though the second answer was factually corrected.

## AI use and verification

Codex assisted with implementation, fixtures, interpretation instructions, and the PDF. Deterministic unit/integration tests, manual raw-to-series spot checks, JSON-to-PDF metric checks, and actual PDF rendering were used to verify its output. Model prose was checked against the saved JSON; the first-run malformed URL was treated as an error rather than accepted because the surrounding numbers were correct.
