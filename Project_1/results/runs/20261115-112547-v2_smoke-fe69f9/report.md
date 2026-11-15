# Field report: v2_smoke

11 documents, 11 groups, 254 fields. Outcomes: correct=29, wrong=22, hallucinated=12, missed=70, true_null=121.
Non-null predictions: 63, precision 46.0%, Wilson-95 error upper bound 65.7%.

## Leave-one-group-out whitelist

Parameters: {"min_n": 3, "min_groups": 1, "evidence": "grounded_text", "conf": 0.0}. Booked **5** values, **1** wrong (Wilson-95 error upper bound 62.4%), 1 families, 4 groups. Net saving: E=20: -5.91%, E=100: -37.40%, E=500: -194.88%.

| evidence | min_n | min_groups | booked | wrong | wilson95 err upper | families | net E=20 | net E=100 | net E=500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| grounded_text | 3 | 1 | 5 | 1 | 62.4% | 1 | -5.91% | -37.40% | -194.88% |
| grounded_text | 5 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 10 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 20 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 3 | 3 | 5 | 1 | 62.4% | 1 | -5.91% | -37.40% | -194.88% |
| grounded_text | 5 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 10 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 20 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 3 | 1 | 5 | 1 | 62.4% | 1 | -5.91% | -37.40% | -194.88% |
| none | 5 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 10 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 20 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 3 | 3 | 5 | 1 | 62.4% | 1 | -5.91% | -37.40% | -194.88% |
| none | 5 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 10 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 20 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |

## Missed savings (correct values not booked, whitelist parameters above)

25 correct values were not booked.

| reason | fields |
|---|---:|
| cell_too_small | 20 |
| cell_has_errors | 5 |

| family | reasons |
|---|---|
| cuad | {"cell_too_small": 12, "cell_has_errors": 5} |
| stem:nport | {"cell_too_small": 4} |
| Schedule K-1 (Form 1120S) Shareholder's Share | {"cell_too_small": 2} |
| Product Spec Sheet / Datasheet — rated specif | {"cell_too_small": 2} |

## Precision tables (non-null predictions only)

### source / kind / grounded_text

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 6 | 6 | 0 | 0 | 100.0% | 39.0% | extractbench / string / True |
| 1 | 1 | 0 | 0 | 100.0% | 79.3% | extractbench / number / True |
| 1 | 1 | 0 | 0 | 100.0% | 79.3% | extractbench / json / True |
| 55 | 21 | 22 | 12 | 38.2% | 73.5% | cuad / span / True |

### route

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 6 | 6 | 0 | 0 | 100.0% | 39.0% | pdf_text_damaged |
| 2 | 2 | 0 | 0 | 100.0% | 65.8% | pdf_text_good |
| 55 | 21 | 22 | 12 | 38.2% | 73.5% | cuad |

### confidence written to preds (rounded)

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 7 | 7 | 0 | 0 | 100.0% | 35.4% | 0.95 |
| 4 | 4 | 0 | 0 | 100.0% | 49.0% | 0.97 |
| 4 | 4 | 0 | 0 | 100.0% | 49.0% | 0.99 |
| 1 | 1 | 0 | 0 | 100.0% | 79.3% | 0.88 |
| 1 | 1 | 0 | 0 | 100.0% | 79.3% | 0.82 |
| 4 | 3 | 1 | 0 | 75.0% | 69.9% | 0.98 |
| 2 | 1 | 1 | 0 | 50.0% | 90.5% | 0.80 |
| 3 | 1 | 2 | 0 | 33.3% | 93.9% | 0.60 |
| 2 | 0 | 2 | 0 | 0.0% | 100.0% | 0.70 |
| 2 | 0 | 1 | 1 | 0.0% | 100.0% | 0.45 |
| 2 | 0 | 1 | 1 | 0.0% | 100.0% | 0.75 |
| 5 | 1 | 3 | 1 | 20.0% | 96.4% | 0.55 |
| 8 | 2 | 2 | 4 | 25.0% | 92.9% | 0.85 |
| 7 | 1 | 1 | 5 | 14.3% | 97.4% | 0.50 |
| 11 | 3 | 8 | 0 | 27.3% | 90.3% | 0.90 |

### family / field (grounded only, n >= 3), safest first

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 4 | 4 | 0 | 0 | 100.0% | 49.0% | cuad / Document Name |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | cuad / Anti-Assignment |
| 4 | 3 | 1 | 0 | 75.0% | 69.9% | cuad / Effective Date |
| 3 | 2 | 0 | 1 | 66.7% | 79.2% | cuad / Termination For Convenience |
| 4 | 2 | 2 | 0 | 50.0% | 85.0% | cuad / Agreement Date |
| 3 | 1 | 2 | 0 | 33.3% | 93.9% | cuad / Exclusivity |
| 3 | 0 | 3 | 0 | 0.0% | 100.0% | cuad / Governing Law |
| 3 | 0 | 1 | 2 | 0.0% | 100.0% | cuad / Ip Ownership Assignment |
| 3 | 0 | 3 | 0 | 0.0% | 100.0% | cuad / Post-Termination Services |
| 4 | 0 | 4 | 0 | 0.0% | 100.0% | cuad / Parties |
