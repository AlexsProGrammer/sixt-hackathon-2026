# Field report: smoke-baseline

12 documents, 11 groups, 306 fields. Outcomes: correct=31, wrong=22, hallucinated=4, missed=93, true_null=156.
Non-null predictions: 57, precision 54.4%, Wilson-95 error upper bound 58.4%.

## Leave-one-group-out whitelist

Parameters: {"min_n": 3, "min_groups": 1, "evidence": "grounded_text", "conf": 0.0}. Booked **0** values, **0** wrong (Wilson-95 error upper bound n/a), 0 families, 0 groups. Net saving: E=20: +0.00%, E=100: +0.00%, E=500: +0.00%.

| evidence | min_n | min_groups | booked | wrong | wilson95 err upper | families | net E=20 | net E=100 | net E=500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| grounded_text | 3 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 5 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 10 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 20 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 3 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 5 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 10 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 20 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 3 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 5 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 10 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 20 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 3 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 5 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 10 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 20 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |

## Missed savings (correct values not booked, whitelist parameters above)

31 correct values were not booked.

| reason | fields |
|---|---:|
| cell_too_small | 31 |

| family | reasons |
|---|---|
| cuad | {"cell_too_small": 20} |
| Schedule K-1 (Form 1065) Partner's Share of I | {"cell_too_small": 4} |
| stem:nport | {"cell_too_small": 4} |
| Product Spec Sheet / Datasheet — rated specif | {"cell_too_small": 2} |
| Schedule K-1 (Form 1120S) Shareholder's Share | {"cell_too_small": 1} |

## Precision tables (non-null predictions only)

### source / kind / grounded_text

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 5 | 5 | 0 | 0 | 100.0% | 43.4% | extractbench / number / True |
| 2 | 0 | 2 | 0 | 0.0% | 100.0% | extractbench / json / True |
| 15 | 6 | 9 | 0 | 40.0% | 80.2% | extractbench / string / True |
| 35 | 20 | 11 | 4 | 57.1% | 59.1% | cuad / span / True |

### route

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 6 | 6 | 0 | 0 | 100.0% | 39.0% | text_ok |
| 16 | 5 | 11 | 0 | 31.2% | 85.8% | text_damaged |
| 35 | 20 | 11 | 4 | 57.1% | 59.1% | cuad_text |

### confidence written to preds (rounded)

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 2 | 2 | 0 | 0 | 100.0% | 65.8% | 0.85 |
| 1 | 1 | 0 | 0 | 100.0% | 79.3% | 0.80 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.99 |
| 17 | 15 | 2 | 0 | 88.2% | 34.3% | 1.00 |
| 12 | 3 | 8 | 1 | 25.0% | 91.1% | 0.90 |
| 24 | 10 | 11 | 3 | 41.7% | 75.5% | 0.95 |

### family / field (grounded only, n >= 3), safest first

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | cuad / Anti-Assignment |
| 3 | 1 | 2 | 0 | 33.3% | 93.9% | cuad / Exclusivity |
