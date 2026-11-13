# Exploratory Data Analysis (Project 1)

Analysis performed strictly on `data/unified/dev.jsonl` (540 documents, 22,115 fields). `data/unified/test_public.jsonl` (176 documents) is held out for evaluation only.

## 1. Dataset Breakdown & Sparsity (Absent vs. Present Fields)

| Dataset | Dev Docs | Total Fields | Present (Non-Null) | Absent (`null`) | Null Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cuad` | 381 | 15,621 | 5,014 | 10,607 | 67.9% |
| `extractbench` | 159 | 6,494 | 4,358 | 2,136 | 32.9% |
| **Total** | **540** | **22,115** | **9,372** | **12,743** | **57.6%** |

**Key takeaway:** Most target fields in a schema are absent (`null`). Because hallucinating a value on a `null` field incurs the full 100x error penalty, abstention on absent fields dominates net savings.

## 2. Field Normalizer Types (`5_score.py`)

| Normalizer (`x-normalizer`) | Field Count | Share | Scoring Rule |
| --- | ---: | ---: | --- |
| `span` | 15,621 | 70.6% | Token F1 >= 0.8 (` | ` separated) |
| `string` | 6,223 | 28.1% | Case-insensitive, collapsed whitespace |
| `json` | 271 | 1.2% | Canonical sorted JSON (all-or-nothing) |

## 3. Document Length, Truncation & Degradation Risks

- **Documents hitting `4_extract_example.py`'s `MAX_CHARS = 60,000` limit:** 109 docs
- **Documents with no extractable PDF text (scanned/image-only):** 66 docs
- **Explicitly corrupted PDFs (`*_corrupted` in `doc_id`):** 7 docs

### Document Condition Tags (`dev.jsonl`)

| Tag | Docs |
| --- | ---: |
| `length:short` | 159 |
| `source:real` | 156 |
| `challenge:T3.a` | 119 |
| `delivery:G1` | 118 |
| `delivery:G4` | 100 |
| `perception:P2` | 68 |
| `domain:D1` | 65 |
| `domain:D2` | 59 |
| `perception:P3` | 27 |
| `challenge:T1.a` | 19 |
| `challenge:T3.e` | 11 |
| `domain:D3` | 11 |
| `domain:D5` | 11 |
| `challenge:T1.e` | 10 |
| `structure:S5` | 10 |

## 4. What the data means for the pipeline

- **Null rate 57.6% (CUAD 67.9%).** Inventing a value for an absent field costs 100. The pipeline therefore treats an explicit null as a normal answer and never fills a field without textual evidence.
- **70.6% of the fields are `span` fields (all CUAD).** The scorer needs token F1 >= 0.8 against the gold clause, and several passages are joined with ` | `. A shortened or paraphrased clause is a wrong value. Offline check: 728 of 734 gold clauses in 60 dev contracts (99.2%) occur verbatim in the contract text, so exact copies can be verified.
- **Document order.** The first 159 records of `dev.jsonl` and the first 47 of `test_public.jsonl` are all ExtractBench. A run with `--limit` below these numbers contains no CUAD contract.
- **Text layers of scanned forms are often damaged.** In the 85 ExtractBench dev documents with a text layer, the median share of gold string values that occur in the text is 71%; in 23 documents it is below 50% (Schedule K-1 family: 23%).
- **`string` fields are compared verbatim** after casefold and whitespace collapse. `1,234.50` is not `1234.50`. Values must be copied as printed.
- **`json` fields (1.2%) are all-or-nothing.** One wrong key or cell makes the whole table wrong.
- **66 of 159 ExtractBench documents (about 41%) have no text layer, 7 are corrupted.** A text-only pipeline can only abstain on them. They are a fixed coverage loss until OCR or a vision model is added.
- **109 of 381 CUAD contracts (about 29%) exceed 60,000 characters.** The starter truncates them. Our pipeline reads the full text in overlapping chunks.

## 5. Reproduce

```
.venv\Scripts\python.exe make_eda.py
```

`make_eda.py` rewrites this whole file with sections 1 to 3. Sections 4 to 6 are written by hand: after a re-run, restore them with `git checkout -- EDA.md` or copy them back. The counts in section 3 use the document reader of the unchanged organiser starter `4_extract_example.py`.

The numbers above come from `data/unified/dev.jsonl` only. `test_public.jsonl` was not analysed here.

## 6. Data credits and licences

We did not create any of the data. Both datasets are downloaded from their original hosts by `1_download.sh` and are not committed to this repository.

| Dataset | Authors and source | Licence | Used here as |
| --- | --- | --- | --- |
| **CUAD v1** (Contract Understanding Atticus Dataset) | The Atticus Project. Hendrycks, Burns, Chen, Ball: "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review", NeurIPS 2021 Datasets and Benchmarks. https://www.atticusprojectai.org/cuad | CC BY 4.0 for the labels. The contracts are public SEC EDGAR filings; the creators give no assurance about their licence status. | 381 dev contracts, 41 clause categories as `span` fields |
| **ExtractBench** (short split) | LlamaIndex (run-llama). https://huggingface.co/datasets/llamaindex/ExtractBench | Apache-2.0. The source PDFs are real public records (for example SEC and regulatory filings). | 159 dev documents (forms, filings, scans) as `string` and `json` fields |

The unified format, the document condition tags and the scorer (`2_prepare.py`, `5_score.py`) are provided by the SIXT hackathon organisers and are unchanged. The licence summary follows the notice printed by `1_download.sh`; the original licence texts are authoritative.
