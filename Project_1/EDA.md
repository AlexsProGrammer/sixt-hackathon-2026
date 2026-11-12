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

- **Documents hitting `4_extract_example.py`'s `MAX_CHARS = 60,000` limit:** 110 docs
- **Documents with no extractable PDF text (scanned/image-only):** 64 docs
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
