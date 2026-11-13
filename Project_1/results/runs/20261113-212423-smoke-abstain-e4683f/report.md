# Field report: smoke-abstain

12 documents, 11 groups, 306 fields. Outcomes: correct=0, wrong=0, hallucinated=0, missed=146, true_null=160.
Non-null predictions: 0, precision n/a, Wilson-95 error upper bound n/a.

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

0 correct values were not booked.

| reason | fields |
|---|---:|

| family | reasons |
|---|---|

## Precision tables (non-null predictions only)

### source / kind / grounded_text

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|

### route

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|

### confidence written to preds (rounded)

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|

### family / field (grounded only, n >= 3), safest first

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
