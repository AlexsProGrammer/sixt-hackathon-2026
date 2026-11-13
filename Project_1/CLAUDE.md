# Project 1 – "Teach a machine to say I don't know" (SIXT Hackathon, 13.11.2026)

Structured extraction from documents (CUAD contracts + ExtractBench forms/scans). For every schema field return
`{"value": ..., "confidence": 0..1}`; `null` = hand to a human.

## The one rule that matters
Human review = cost 1, wrong/hallucinated auto-booked value = cost 100. Auto-booked fields need >99% precision.
Abstaining is cheap, a confident mistake is expensive. Optimise **net_saving_pct at our declared threshold**, not accuracy.

## Deadline & deliverables (push by 16:45)
- Code in `Project_1/`, `run_hidden.sh <input.jsonl> <output.jsonl>` must call our final extractor (hidden test has NO `gold` key)
- `SUBMISSION.md` (template `../SUBMISSION_TEMPLATE.md`): approach, results, how to run, "Models and why" table, **declared threshold**, required env vars
- `EDA.md` (exists), `submission/demo.mp4` (≤1 min, <50 MB) or `submission/slides.pdf` (≤5 slides)
- Metrics: net saving, precision, coverage, hallucination rate; sensitivity at error cost 20x / 500x

## Commands (run inside Project_1/, .venv active, Python 3.12)
```
python 4_extract_example.py --data data/unified/dev.jsonl --out results/x_dev.jsonl --limit 10 --mode llm
python 5_score.py --gold data/unified/dev.jsonl --pred results/x_dev.jsonl --threshold 0.95 --json results/x_dev_score.json
python test_score.py
```
LLM config in `.env`: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` (OpenAI-compatible).

## Hard rules
- Never commit `.env`, `data/`, `cache/`, `results/*.jsonl`, API keys
- Never tune prompts, calibration or threshold on `test_public.jsonl` – use `dev.jsonl` (split dev_train/dev_cal)
- Every non-null prediction MUST have an explicit `confidence` (missing = 1.0 = auto-accepted!)
- Iterate over `rec["schema"]["properties"]`, never over `rec["gold"]`
- Don't run code from inside `data/raw/` (untrusted downloads)
- Keep model, K samples, workers, threshold configurable via CLI/env

## Data traps (details in docs/)
- ExtractBench fields use `string` normalizer: copy numbers/dates verbatim ("1,234.50" ≠ "1234.50")
- Unchecked visible checkbox = `"false"`, absent section = `null`
- ~29% of CUAD contracts > 60k chars (starter truncates at MAX_CHARS)
- ~40% of ExtractBench PDFs have no text layer (scans), some are `*_corrupted`
- `json` fields are all-or-nothing → abstain unless samples agree

## probly (uncertainty quantification, needs Python ≥3.12)
- `from probly.representation.distribution import CategoricalDistribution`
- `from probly.representation.credal_set import CredalSet, ProbabilityIntervalsCredalSet`
- also `probly.quantification`, `probly.calibrator`

## Team docs (read before larger changes)
- `docs/hackathon_master_plan_team_kickoff.md` – plan, roles, phases/checkpoints
- `docs/data_reference_baselines_scoring_guide.md` – data, traps, score.py output, baselines
- `docs/engineering_roadmap_refactoring_llm_cache.md` – 6 starter bugs, module layout, disk cache
- `docs/probly_integration_uncertainty_quantification_guide.md` – UQ pipeline, calibration, conformal threshold

## Working style
"Just make it exist first, make it good later." Keep the pipeline end-to-end runnable, score after every change,
save `results/<checkpoint>_score.json`. Small commits, `git pull` before starting.
