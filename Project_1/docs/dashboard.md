# Project 1 Dashboard (T12)

Local Streamlit web application for running small extraction batches, reviewing documents side-by-side with extracted values and gold, recording human review actions, and inspecting analytics across stored and session runs.

The dashboard is an **optional** component: `4_extract.py`, `5_score.py`, and `run_hidden.sh` never import or depend on it.

## Installation

From `Project_1/`:

```bash
.venv/bin/pip install -r requirements-dashboard.txt
```

Pinned packages: `streamlit==1.67.0`, `pandas==3.1.1`, `altair==6.3.0`.

## Starting the Dashboard

From `Project_1/`:

```bash
.venv/bin/streamlit run dashboard/app.py --server.address 127.0.0.1
```

It binds to `127.0.0.1` only. Document text never leaves the machine except through the configured LLM endpoint.

## Pages

1. **Run**: Select `dev`, `test_public`, a split (`fit`, `select`, `audit`, `audit2`, `smoke`), a single `doc_id`, a stratified random sample (with reproducible seed), or upload a PDF + schema JSON. Runs execute in a background thread with live progress and stay in session state (`tags=["session"]`) until you click **Save to registry**.
2. **Review**: Pick a run and document. Left pane renders the PDF (via `st.pdf`, base64 `<iframe>`, or `pdftoppm` PNGs) or CUAD contract text (predicted spans highlighted, gold spans underlined). Right pane shows per-field values, gold, confidence, decision (`booked` / `to human`), reason, evidence flags, and per-view observations, with **Accept**, **Decline**, and **Edit** buttons writing to `results/reviews.jsonl`.
3. **Analytics**: Run comparison table, precision vs coverage curve, net saving vs threshold (`E=20/100/500`), reliability chart, route/kind breakdown bars, and family × field heatmap. Unsaved session runs are overlaid with dashed lines.
4. **Latest run**: Manifest summary (models, routes, prompt versions, selector SHA-256, requests/cache hits per model, time per doc, failures) and business headline (`X% of fields need no human; net saving Y at E=100; Z errors`).
