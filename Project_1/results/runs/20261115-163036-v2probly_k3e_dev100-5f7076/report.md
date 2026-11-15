# Field report: v2probly_k3e_dev100

20 documents, 14 groups, 1041 fields. Outcomes: correct=22, wrong=6, hallucinated=1, missed=623, true_null=389.
Non-null predictions: 29, precision 75.9%, Wilson-95 error upper bound 42.1%.

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

22 correct values were not booked.

| reason | fields |
|---|---:|
| cell_too_small | 22 |

| family | reasons |
|---|---|
| Form 1099-B Proceeds From Broker and Barter E | {"cell_too_small": 13} |
| stem:13f | {"cell_too_small": 4} |
| Schedule K-1 (Form 1120S) Shareholder's Share | {"cell_too_small": 3} |
| Schedule K-1 (Form 1065) Partner's Share of I | {"cell_too_small": 2} |

## Precision tables (non-null predictions only)

### source / kind / grounded_text

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 7 | 6 | 0 | 1 | 85.7% | 51.3% | extractbench / number / True |
| 3 | 1 | 2 | 0 | 33.3% | 93.9% | extractbench / json / True |
| 19 | 15 | 4 | 0 | 78.9% | 43.3% | extractbench / string / True |

### route

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 4 | 4 | 0 | 0 | 100.0% | 49.0% | pdf_text_good |
| 25 | 18 | 6 | 1 | 72.0% | 47.6% | pdf_text_damaged |

### confidence written to preds (rounded)

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 3 | 0 | 2 | 1 | 0.0% | 100.0% | 0.42 |
| 26 | 22 | 4 | 0 | 84.6% | 33.5% | 1.00 |

### family / field (grounded only, n >= 3), safest first

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Form 1099-B Proceeds From Broker and Barter E / payer_federal_id |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Form 1099-B Proceeds From Broker and Barter E / recipient_name |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Form 1099-B Proceeds From Broker and Barter E / recipient_tax_id |
| 3 | 2 | 1 | 0 | 66.7% | 79.2% | Form 1099-B Proceeds From Broker and Barter E / account_number |
