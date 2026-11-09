# Project 1: Teach a machine to say "I don't know"
*Structured extraction from documents: turn messy PDFs, scans and photos into JSON, and know which fields to trust.*

**Project owners:** Sruthi Radhakrishnan, Ihsan Soydemir. Questions before the hackathon: sruthi.radhakrishnan@sixt.com, ihsan.soydemir@sixt.com. On the day, ask on site.

## The story
Every day documents arrive: invoices, contracts, forms, scans, handwriting, phone photos. Today people read them and type the values into a system. An AI can do it in seconds, but there is a catch: **one confidently wrong value that reaches the system of record costs far more than the minute a person would have spent.** So the useful system is not the one that answers most often. It is the one that **knows when it is right**: it books the fields it is sure of, and hands the rest to a human.

You are building that decision. For every field, extract a value and a confidence. We then ask one question: *does your automation actually save money?*

## The task: structured extraction from documents
You get a document (a PDF, a scan, a phone photo, a contract) and a schema: a list of fields such as `invoice_number`, `due_date`, `total`, or a contract clause. You return the value of each field as JSON, together with how sure you are. A field that is not in the document must come back empty.

That sounds simple, and it is where AI systems struggle. Layouts vary, scans are bad, handwriting and checkboxes get misread, and models happily invent a plausible value for a field that is blank. So the work has two halves: extracting well, and knowing which extractions to trust.

Here is the whole setup in one picture:

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

## The business case, in numbers
We use a simple cost model (the numbers are assumptions you can change, not SIXT figures): a human reviewing one field costs **1**, a wrong value that gets booked costs **100**.

> At that ratio, automating a field only pays off if you are right more than **99%** of the time. That is where the 99% target comes from.

`5_score.py` reports your **net saving versus reviewing every field by hand**. A system that guesses on everything loses money, and one that stays quiet saves nothing. The interesting part is the point in between, on documents that are actually messy.

**A quick example.** Say 1,000 fields come in. By hand that costs 1,000. Your system accepts 900 of them and sends 100 to a human:
- 4 accepted values are wrong (99.6% right): cost is 100 reviews + 4 x 100 = **500**. You save **50%**.
- 20 accepted values are wrong (97.8% right): cost is 100 + 20 x 100 = **2,100**. You **lose** more than twice what you started with.

Same system, a few more mistakes, and the business case flips. That's why confidence matters more than raw accuracy. In a small trial with two off-the-shelf LLMs (21 documents), the net saving ranged from about 10% to 24%. The big difference was how often each one confidently invented a value for a field that wasn't there.

Four outcomes, counted differently:

| Outcome | Meaning | Cost |
| --- | --- | --- |
| wrong | accepted value differs from gold | the full error cost |
| hallucinated | accepted value, but the field is truly absent | the full error cost, and the one that hurts trust most |
| missed | no value given, but the field is there | only a human review |
| true null | no value given, and the field is truly absent | only a human review (no saving, no loss) |

## Quick start
The number in each script is the order to run it in (use `python3` if `python` is not found).
```bash
bash 1_download.sh        # about 135 MB, asks you to accept the dataset licences
python 2_prepare.py       # builds data/unified/dev.jsonl and test_public.jsonl
python 3_baseline.py --train data/unified/dev.jsonl --target data/unified/test_public.jsonl --out preds.jsonl
python 4_extract_example.py --data data/unified/dev.jsonl --out preds.jsonl --limit 10   # starter extractor, no key needed
python 5_score.py --gold data/unified/dev.jsonl --pred preds.jsonl --threshold 0.95
```
Python 3.11+, standard library only; `pip install -r requirements.txt` is optional (`jsonschema` for a schema-validity line, `pypdf` so step 4 can read PDFs). Step 4 uses crude keyword rules by default, which score about nothing and just show the pipeline. The starter is deliberately naive, so read its code before you build on it. Set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` (any OpenAI-compatible endpoint) and it uses an LLM instead. A key is optional: bring your own, or build without one (SIXT access is not confirmed). Never commit secrets (use `.env`) or `data/`, and don't run code from inside `data/raw/`. `python test_score.py` checks the scorer.

You may start early: once you have the invite, run steps 1 to 3 at home already if you are keen and look at the data. It is a one-day hackathon with a 16:45 deadline.

## Data
**881 labelled documents (about 26,000 fields) to work on, plus a hidden test we keep.** Four public English datasets. You download them yourself from the original hosts, this repo redistributes nothing. All licences are permissive (checked 2026-11-09, not legal advice).

| Dataset | Docs | What's in it | Licence |
| --- | --- | --- | --- |
| [**ExtractBench**](https://huggingface.co/datasets/llamaindex/ExtractBench) (main) | 206 | Real forms and scans, handwriting, checkboxes | Apache-2.0 |
| [CUAD](https://www.atticusprojectai.org/cuad) | 510 | Contracts, 41 clause types | CC BY 4.0 |
| [InvoiceBenchmark](https://huggingface.co/datasets/jngb-labs/InvoiceBenchmark) | 200 | Invoices, 80 with a wrong printed total | MIT |
| [invoice-extraction-benchmark](https://huggingface.co/datasets/drew-ipp/invoice-extraction-benchmark) | 181 | Invoices with scan damage | CC BY 4.0 |

Each record in `data/unified/*.jsonl` has `doc_id`, `pages` (path relative to `data/`), `schema`, `gold` (null = not in the document) and `tags`. For CUAD, `pages` is the shared `CUADv1.json` and the contract is the entry whose `title` is the `doc_id` without `cuad:`. The final score uses a hidden test from the same datasets, so tune on dev only.

*A few things to check before you trust the data: Is every printed number the right one? What does an empty checkbox mean? Does every document fit in a prompt? Where are the blanks?*

## How scoring works
A field is **accepted** if its value is non-null and `confidence >= threshold` (a missing confidence counts as 1.0, so always send one). In `gold`, null means absent from the document; in your prediction, null means "no answer, a human reviews it". Values are compared by the field's `x-normalizer`:

| Normalizer | Compared as |
| --- | --- |
| `string` (also the default, e.g. all ExtractBench fields) | case-insensitive, whitespace collapsed |
| `id` | letters and digits only |
| `amount` | as a number: `1.234,50` = `1,234.50`; `20%` = `0.20` |
| `date` | common formats, as `YYYY-MM-DD` |
| `span` (CUAD) | token F1 >= 0.8; several gold answers are joined with ` \| ` |
| `json` (nested, about 2% of fields) | exact match of the whole value; answering null is fine |

`5_score.py` prints precision, coverage, hallucination rate and **net saving** (`--review-cost` and `--error-cost`, default 1 and 100). Net saving at your declared threshold is the headline result; the sweep over all thresholds is for choosing it on dev.

## What you submit
Push all of this to your repo by 16:45:

| # | What | Where |
| --- | --- | --- |
| 1 | Your code, with `run_hidden.sh` calling your extractor | `Project_1/` |
| 2 | `SUBMISSION.md`: approach, results, how to run, the "Models and why" table, **your threshold** | `Project_1/` ([template](../SUBMISSION_TEMPLATE.md)) |
| 3 | `EDA.md`: a short look at the data, with real numbers | `Project_1/` |
| 4 | A 1-minute video or up to 5 slides | `submission/demo.mp4` or `submission/slides.pdf` |

**Hidden test:** we run `bash run_hidden.sh <input.jsonl> <output.jsonl>` from your `Project_1/` folder (dev format without `gold`, `data/raw/` provided) and score the output at exactly your threshold. `run_hidden.sh` ships calling the starter; point it at your extractor. List the environment variables it needs in `SUBMISSION.md` and tell us before the deadline if you need a key.

**Predictions:** one JSON per line; a null value means "no answer".
```json
{"doc_id": "invoicebenchmark:INV-2026-0001", "fields": {"total": {"value": "1190.00", "confidence": 0.93}, "due_date": {"value": null}}}
```
`3_baseline.py` has two no-AI references: never answer (saves nothing) and always give the most common value (loses money unless the threshold is high). A real system has to beat the second one.

## Directions to think about
Not a checklist. Just things worth asking yourself.

**Which model, and why?** Any model is allowed, open-weight or closed. You should be able to defend your pick, so show us the comparison on the same dev documents.
- Don't stop at accuracy. How often does it confidently make up a value for a blank field? With a 100x error cost, that hurts more than a few points of accuracy.
- Does its confidence mean anything? When it says 0.95, is it right 95% of the time?
- What does a document cost in money and seconds? Maybe a cheap model first, and a stronger one only when it's unsure?
- Text or vision? A clean PDF and a blurry photo might need different routes.

**Make the value prove itself.** Does it actually show up in the document? Do the numbers add up (`subtotal + tax = total`)? If a printed number looks wrong, what should your system do?

**Use doubt as a signal.** Ask two models, or ask twice. If they disagree, lower the confidence. Let "no answer" be a real answer. Which fields would you never automate?

**Deal with ugly inputs.** Rotate, zoom, crop, try another OCR. And what happens when a scan is just unreadable?

**Agents fit nicely.** Extract, check, fix, repeat. Give them tools (OCR, a calculator, zoom). Route documents by type or quality. Or start with a cheap model and escalate only when it's unsure.

**Knowledge graph? Optional.** It can spot conflicts across documents, or check that line items add up to the total. If you use one, show before and after: did precision, coverage or savings really improve?

**Prove the business value.** This is where you convince us.
- Show your net saving, and how it moves if a wrong value costs 20x or 500x instead of 100x.
- Show how much runs with no human and how much goes to review.
- Say what the model costs per document, and whether that eats your savings.
- Say which fields you'd keep manual, and how you'd roll it out.

## How you are judged
The general criteria are on the back of the hackathon handout. For this project, "Results" means net saving, precision, coverage and hallucination rate at your threshold, on data you did not tune on.

## Credits
Keep these in anything you publish. We converted all four datasets to one format.
- Zhang, Lyjak, Stewart, Li, Suo (2026). *ExtractBench: A Benchmark for Schema-Guided Enterprise Document Extraction.* arXiv:2607.29677.
- Hendrycks, Burns, Chen, Ball (2021). *CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review.* NeurIPS Datasets and Benchmarks.
- Neugebauer, J. (2026). *InvoiceBenchmark.* jngb-labs.
- InvoiceParser Pro (2026). *invoice-extraction-benchmark.*
