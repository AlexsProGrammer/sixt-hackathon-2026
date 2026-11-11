# Project 1: Teach a machine to say "I don't know"
*Structured extraction from documents: turn messy PDFs and scans into JSON, and know which fields to trust.*

**Project owners:** Sruthi Radhakrishnan, Ihsan Soydemir (sruthi.radhakrishnan@sixt.com, ihsan.soydemir@sixt.com). On the day, ask on site.

## The story
Every day documents arrive: contracts, forms, scans, handwriting. Today people read them and type the values into a system. An AI can do it in seconds, but there is a catch: **one confidently wrong value that reaches the system of record costs far more than the minute a person would have spent.** So the useful system is not the one that answers most often. It is the one that **knows when it is right**: it books the fields it is sure of and hands the rest to a human.

## The task
You get a document and a schema (a list of fields, e.g. a contract clause or a form box). For every field, return a **value and a confidence**. A field that is not in the document must come back empty.

```
+---------------------------+   +---------------------------+
|          document         |   |           schema          |
|      PDF, scan, photo     |   |     the fields to fill    |
+-------------+-------------+   +-------------+-------------+
              |                               |
              +---------------+---------------+
                              |
                              v
              +-------------------------------+
              |          YOUR SYSTEM          |
              |      model, tools, checks     |
              +-------------------------------+
                              |
     a value + a confidence, for every field
                              |
                              v
              +-------------------------------+
              | confidence >= your threshold? |
              +-+---------------------------+-+
                |                           |
               yes                          no
                v                           v
    +-----------------------+   +-----------------------+
    |  booked automatically |   |    sent to a human    |
    | right: saves a review |   |     costs 1 review    |
    |    wrong: costs 100   |   |   (the safe choice)   |
    +-----------+-----------+   +-----------+-----------+
                |                           |
                +-------------+-------------+
                              |
                              v
      5_score.py: net saving vs. doing it all by hand
```

This is where models struggle: layouts vary, scans are bad, handwriting and checkboxes get misread, and models happily invent a plausible value for a blank field.

## The business case
Everyone is scored with the same fixed costs (a simplified model, not SIXT figures): a human review of one field costs **1**, a wrong value that gets booked costs **100**. So automating only pays off if you are right more than **99%** of the time.

Example with 100 fields. Doing it all by hand costs 100. Your system books 90 and sends 10 to a human (cost 10):
- all 90 booked values are right: you pay 10 and save **90%**.
- just 1 booked value is wrong: you pay 10 + 100 = 110, which is **more than by hand**.

One confident mistake can wipe out the saving. That is why knowing when you are right matters more than raw accuracy.

| Outcome | Meaning | Cost |
| --- | --- | --- |
| wrong | accepted value differs from gold | error cost |
| hallucinated | accepted value, but the field is truly absent | error cost, hurts trust most |
| missed | no value, but the field is there | one review |
| true null | no value, field truly absent | one review (no saving, no loss) |

## Quick start

<img src="../assets/time-quick-setup.svg" alt="Under 5 minutes" width="360">

**Quick setup (under 5 min):** `bash setup.sh` in this folder. It makes a virtual environment, downloads the data (add `--accept-licenses` to accept the dataset licences) and runs the baseline. Copy `.env.example` to `.env` for your LLM key. Python is our starting point; any language is fine.

Or step by step:
```bash
bash 1_download.sh        # about 60 MB, asks you to accept the dataset licences
python 2_prepare.py       # builds data/unified/dev.jsonl and test_public.jsonl
python 3_baseline.py --train data/unified/dev.jsonl --target data/unified/test_public.jsonl --out preds.jsonl
python 4_extract_example.py --data data/unified/dev.jsonl --out preds.jsonl --limit 10   # naive starter
python 5_score.py --gold data/unified/dev.jsonl --pred preds.jsonl --threshold 0.95
```
Python 3.11+, standard library only (use `python3` if `python` is not found). `pip install -r requirements.txt` is optional (`jsonschema`, `pypdf` so step 4 can read PDFs). The starter uses crude keyword rules and scores about nothing: read it before building on it.

**LLM access:** we email you an API key, endpoint URL and model list on site. Put them in `.env` as `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` (any OpenAI-compatible endpoint) and the starter uses them. You can also bring your own key. Never commit secrets or `data/`, and don't run code from inside `data/raw/`.

You may start early: run steps 1 to 3 at home and look at the data. It is a one-day hackathon with a **16:45 deadline**.

## Data
**565 labelled documents (about 23,000 fields), plus a hidden test we keep.** Downloaded by you from the original hosts; this repo redistributes nothing. Licences are permissive (checked 2026-11-09, not legal advice).

| Dataset | Docs | What's in it | Licence |
| --- | --- | --- | --- |
| [CUAD](https://www.atticusprojectai.org/cuad) | 510 | Contracts, 41 clause types | CC BY 4.0 |
| [ExtractBench](https://huggingface.co/datasets/llamaindex/ExtractBench) | 206 | Real forms and scans, handwriting, checkboxes | Apache-2.0 |

Each record in `data/unified/*.jsonl` has `doc_id`, `pages` (path relative to `data/`), `schema`, `gold` (null = not in the document) and `tags`. For CUAD, `pages` is the shared `CUADv1.json` and the contract is the entry whose `title` is the `doc_id` without `cuad:`. The hidden test comes from the same datasets, so tune on dev only.

*Check before you trust the data: what does an empty checkbox mean? Does every document fit in a prompt? Where are the blanks?*

## Scoring
A field is **accepted** if its value is non-null and `confidence >= threshold` (a missing confidence counts as 1.0, so always send one). In your prediction, null means "no answer, a human reviews it". Values are compared as:

| Field type | Compared as |
| --- | --- |
| `string` (default, all ExtractBench fields) | case-insensitive, whitespace collapsed |
| `span` (CUAD) | token F1 >= 0.8; several gold answers are joined with ` \| ` |
| `json` (nested, about 2% of fields) | exact match of the whole value; null is fine |

`5_score.py` prints precision, coverage, hallucination rate and **net saving** (always at 1 and 100; the `--review-cost` and `--error-cost` flags are only for your own what-if analysis). Net saving at your declared threshold is the headline result; the sweep over thresholds is for choosing it on dev. `python test_score.py` checks the scorer. `3_baseline.py` has two no-AI references (never answer, or always the most common value); a real system must beat the second one.

## What you submit (by 16:45, pushed to your repo)
| What | Where |
| --- | --- |
| Your code, with `run_hidden.sh` calling your extractor | `Project_1/` |
| `SUBMISSION.md`: approach, results, how to run, "Models and why" table, **your threshold** ([template](../SUBMISSION_TEMPLATE.md)) | `Project_1/` |
| `EDA.md`: a short look at the data, with real numbers | `Project_1/` |
| A 1-minute video or up to 5 slides | `submission/demo.mp4` or `submission/slides.pdf` |

**Hidden test:** we run `bash run_hidden.sh <input.jsonl> <output.jsonl>` from `Project_1/` (dev format without `gold`, `data/raw/` provided) and score at exactly your threshold. List the environment variables it needs in `SUBMISSION.md`.

**Input:** one JSON per line. Dev and public test include `gold`; the hidden test has the same format without it. Shortened example:
```json
{"doc_id": "cuad:LIMEENERGYCO_09_09_1999-EX-10-DISTRIBUTOR AGREEMENT", "pages": ["raw/cuad/CUADv1.json"],
 "schema": {"properties": {"Agreement Date": {"type": "string", "x-normalizer": "span"},
                           "Governing Law": {"type": "string", "x-normalizer": "span"},
                           "Non-Compete": {"type": "string", "x-normalizer": "span"}}},
 "gold": {"Agreement Date": "7th day of September, 1999.", "Governing Law": "This Agreement is to be construed according to the laws of the State of Illinois.", "Non-Compete": null}}
```
**Output (your predictions):** one JSON per line, one entry per schema field. For span fields, copy the text from the contract; null means "no answer".
```json
{"doc_id": "cuad:LIMEENERGYCO_09_09_1999-EX-10-DISTRIBUTOR AGREEMENT", "fields": {
  "Agreement Date": {"value": "7th day of September, 1999.", "confidence": 0.93},
  "Governing Law": {"value": "This Agreement is to be construed according to the laws of the State of Illinois.", "confidence": 0.90},
  "Non-Compete": {"value": null}}}
```
(On disk each record is a single line; it is wrapped here to read.)

## Directions to think about
Not a checklist, just things worth asking.
- **Which model, and why?** Any model is allowed. Compare on the same dev documents, and not only on accuracy: how often does it invent a value for a blank field? Is 0.95 confidence right 95% of the time? What does a document cost in money and seconds?
- **Make the value prove itself.** Does it actually appear in the document? Can a cheap model go first and a stronger one only when it's unsure?
- **Use doubt as a signal.** Ask twice or ask two models; if they disagree, lower the confidence. Which fields would you never automate?
- **Ugly inputs.** Rotate, zoom, try another OCR, or read a page as an image. What happens when a scan is unreadable?
- **Agents and knowledge graphs** are welcome (extract, check, fix, repeat; tools such as OCR or zoom), but show before and after: did precision, coverage or savings really improve?
- **Prove the business value.** Show net saving, and how it moves if a wrong value costs 20x or 500x. Show how much runs with no human, what the model costs per document, which fields you'd keep manual, and how you'd roll it out.

## How you are judged
The general criteria are on the back of the hackathon handout. Here, "Results" means net saving, precision, coverage and hallucination rate at your threshold, on data you did not tune on.

## Credits
Keep these in anything you publish. We converted both datasets to one format.
- Zhang, Lyjak, Stewart, Li, Suo (2026). *ExtractBench: A Benchmark for Schema-Guided Enterprise Document Extraction.* arXiv:2607.29677.
- Hendrycks, Burns, Chen, Ball (2021). *CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review.* NeurIPS Datasets and Benchmarks.
