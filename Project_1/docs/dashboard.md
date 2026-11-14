# Project 1 — Local Extraction & UQ Dashboard (v2)

The dashboard is an optional local web UI built with Streamlit (`1.67.0`) for running extractions, reviewing document fields, comparing UQ methods, and inspecting run artifacts. CLI scripts (`4_extract.py`, `5_score.py`, `run_hidden.sh`, `evaluation/*`, `pipeline/*`, `uncertainty/*`) never import it.

## Starting the dashboard

From `Project_1/`:

```bash
.venv/bin/pip install -r requirements-dashboard.txt
.venv/bin/streamlit run dashboard/app.py --server.address 127.0.0.1
```

Theme and server defaults live in `.streamlit/config.toml`.

## Pages

1. **Home** (`dashboard/views/home.py`): Project showcase with the cost model (`Human = 1`, `Booked correct = 0`, `Booked wrong = 100`), live benchmark KPIs from a selected showcase run, a dynamic Mermaid pipeline diagram reflecting the active decision file, models, routes, and declared threshold τ, plus the model/route matrix and UQ method explainers.
2. **Run** (`dashboard/views/run.py`): Two-column Run Builder + live Run Preview. Supports `Random N`, `Single doc`, `Full split`, and `Upload` inputs; validates UQ method / sample count K combinations before launch; previews routes, models, estimated calls, and reply-cache status; streams live per-doc progress KPIs and shows a post-run result card.
3. **Review** (`dashboard/views/review.py`): Side-by-side document viewer and extracted fields table with row selection detail drawer, shared decision filters (`All`, `Only booked`, `Only to human`, `Only missed savings`, `Only errors`), and an interactive **Review queue** (`dashboard/components/review_queue.py`) with per-row **Accept** (`✓`), **Edit** (`✎`), and **Decline** (`⦸`) icon buttons, bulk "Accept all booked", pagination, and CSV export.
4. **Analytics** (`dashboard/views/analytics.py`): Five sub-tabs (**Overview**, **Methods**, **Curves**, **Field diagnostics**, **Compare two runs**) with an `E ∈ {20, 100, 500}` error-cost selector, success verdicts, curve-wide average precision and net saving tables, UQ method leaderboard, signal quality charts (agreement, entropy, grounding), reliability diagrams, route/kind breakdowns, family×field heatmap, and field-level run diffs.
5. **Run details** (`dashboard/views/latest.py`): Hero business headline, KPI row, metadata & provenance grid, per-model request/cache-hit bars, score breakdowns (`by_source`, `by_condition`), downloadable artifacts, and generate buttons.

## Sidebar & global settings

- **Active context**: active run badge, session run count, LLM endpoint status (without exposing API keys), and reply cache size.
- **Quick actions**: jump to Run, open active run in Review, or clear cached data.
- **Settings** (pinned at the bottom): **Decision file** selector and **Declared threshold τ** slider, plus a one-click helper to match the decision file's threshold.

## Success definition

- **Human-only baseline**: `0.0%` net saving (every field reviewed by a human at cost `1`).
- **Net saving**: `(accepted - E * errors) / n_fields`, where `errors = wrong + hallucinated`.
- **Break-even precision**: `E / (E + 1)` (`95.2%` at `E=20`, `99.0%` at `E=100`, `99.8%` at `E=500`).
- **Verdict**:
  - `Full success`: `accepted > 0`, `precision >= τ`, and `net_saving > 0`.
  - `Partial`: `net_saving > 0` below `τ`, or `precision >= τ` with `0` net saving.
  - `Not yet`: `net_saving < 0`.

## Generate actions (`dashboard/actions.py`)

Empty states and artifact panels offer whitelisted CLI buttons (`shell=False`, validated run IDs):

| Action | CLI executed |
|---|---|
| Build field table | `python -m evaluation.field_table <run>` |
| Re-score at τ | `python -m evaluation.registry score <run> --threshold <τ>` |
| Generate report | `python -m evaluation.report --run <run>` |
| Generate diff report | `python -m evaluation.report --run <B> --diff <A> <B>` |
| Rebuild index | `python -m evaluation.registry rebuild` |
| Import legacy runs | `python tools/import_legacy_runs.py` |
| Generate comparison plots | `python tools/compare_results.py` |

## Mermaid diagram (offline support)

`dashboard/components/mermaid.py` prefers a vendored `dashboard/assets/mermaid.min.js` when present, falling back to jsDelivr CDN and a Graphviz DOT fallback. To vendor Mermaid locally:

```bash
curl -L -o dashboard/assets/mermaid.min.js https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js
```

## Troubleshooting

- **Double-click navigation**: Fixed in v2 by replacing the sidebar `st.radio` with `st.navigation(..., position="top")` and `st.switch_page`.
- **Dark mode**: `.streamlit/config.toml` sets `base = "light"` with semantic badge palettes for consistent contrast.
