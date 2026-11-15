# Field report: v2probly_k1_dev100

97 documents, 68 groups, 5150 fields. Outcomes: correct=247, wrong=40, hallucinated=6, missed=2940, true_null=1917.
Non-null predictions: 293, precision 84.3%, Wilson-95 error upper bound 20.3%.

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

247 correct values were not booked.

| reason | fields |
|---|---:|
| cell_too_small | 247 |

| family | reasons |
|---|---|
| Form 1099-B Proceeds From Broker and Barter E | {"cell_too_small": 60} |
| ClosingDisclosureTRID | {"cell_too_small": 43} |
| CCCMarketValuationReport | {"cell_too_small": 32} |
| Schedule K-1 (Form 1120S) Shareholder's Share | {"cell_too_small": 28} |
| RRCW1Extraction | {"cell_too_small": 25} |
| RRCW14ReviewExtraction | {"cell_too_small": 17} |
| Schedule K-1 (Form 1065) Partner's Share of I | {"cell_too_small": 15} |
| stem:13f | {"cell_too_small": 14} |
| MitchellVehicleValuationReport | {"cell_too_small": 10} |
| Product Spec Sheet / Datasheet — rated specif | {"cell_too_small": 3} |

## Precision tables (non-null predictions only)

### source / kind / grounded_text

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 44 | 41 | 2 | 1 | 93.2% | 18.2% | extractbench / number / True |
| 23 | 14 | 8 | 1 | 60.9% | 59.2% | extractbench / json / True |
| 226 | 192 | 30 | 4 | 85.0% | 20.3% | extractbench / string / True |

### route

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 116 | 112 | 4 | 0 | 96.6% | 8.5% | pdf_text_good |
| 177 | 135 | 36 | 6 | 76.3% | 30.5% | pdf_text_damaged |

### confidence written to preds (rounded)

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 90 | 90 | 0 | 0 | 100.0% | 4.1% | 0.99 |
| 34 | 34 | 0 | 0 | 100.0% | 10.2% | 0.95 |
| 34 | 34 | 0 | 0 | 100.0% | 10.2% | 0.97 |
| 2 | 2 | 0 | 0 | 100.0% | 65.8% | 0.88 |
| 34 | 33 | 1 | 0 | 97.1% | 14.9% | 0.98 |
| 8 | 7 | 1 | 0 | 87.5% | 47.1% | 0.85 |
| 4 | 3 | 1 | 0 | 75.0% | 69.9% | 0.60 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.38 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.65 |
| 1 | 0 | 0 | 1 | 0.0% | 100.0% | 0.40 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.72 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.58 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.56 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.20 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.28 |
| 9 | 7 | 2 | 0 | 77.8% | 54.7% | 0.80 |
| 4 | 2 | 2 | 0 | 50.0% | 85.0% | 0.50 |
| 2 | 0 | 2 | 0 | 0.0% | 100.0% | 0.35 |
| 5 | 1 | 4 | 0 | 20.0% | 96.4% | 0.75 |
| 4 | 0 | 3 | 1 | 0.0% | 100.0% | 0.45 |
| 7 | 1 | 5 | 1 | 14.3% | 97.4% | 0.55 |
| 38 | 31 | 4 | 3 | 81.6% | 33.4% | 0.90 |
| 10 | 2 | 8 | 0 | 20.0% | 94.3% | 0.70 |

### family / field (grounded only, n >= 3), safest first

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 13 | 13 | 0 | 0 | 100.0% | 22.8% | Form 1099-B Proceeds From Broker and Barter E / payer_federal_id |
| 13 | 13 | 0 | 0 | 100.0% | 22.8% | Form 1099-B Proceeds From Broker and Barter E / recipient_name |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | Form 1099-B Proceeds From Broker and Barter E / payer_name |
| 5 | 5 | 0 | 0 | 100.0% | 43.4% | Schedule K-1 (Form 1120S) Shareholder's Share / box_1_ordinary_business_income |
| 4 | 4 | 0 | 0 | 100.0% | 49.0% | Schedule K-1 (Form 1120S) Shareholder's Share / shareholder_name |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Schedule K-1 (Form 1065) Partner's Share of I / capital_current_year_increase_decrease |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Schedule K-1 (Form 1065) Partner's Share of I / box_1_ordinary_business_income |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Schedule K-1 (Form 1120S) Shareholder's Share / irs_center |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Schedule K-1 (Form 1120S) Shareholder's Share / shareholder_stock_ownership_pct |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:13f / filing_manager_name |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:13f / report_type |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:13f / table_entry_total |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:13f / table_value_total_usd |
| 6 | 5 | 1 | 0 | 83.3% | 56.4% | Schedule K-1 (Form 1120S) Shareholder's Share / box_15_amt_items |
| 14 | 12 | 2 | 0 | 85.7% | 39.9% | Form 1099-B Proceeds From Broker and Barter E / account_number |
| 13 | 11 | 2 | 0 | 84.6% | 42.2% | Form 1099-B Proceeds From Broker and Barter E / recipient_tax_id |
| 7 | 4 | 3 | 0 | 57.1% | 75.0% | Schedule K-1 (Form 1120S) Shareholder's Share / corporation_name |
| 3 | 0 | 3 | 0 | 0.0% | 100.0% | Schedule K-1 (Form 1065) Partner's Share of I / partner_name |
| 3 | 0 | 0 | 3 | 0.0% | 100.0% | Schedule K-1 (Form 1065) Partner's Share of I / capital_account_method |
| 3 | 0 | 3 | 0 | 0.0% | 100.0% | Schedule K-1 (Form 1065) Partner's Share of I / box_14_self_employment_earnings |
| 4 | 0 | 4 | 0 | 0.0% | 100.0% | Schedule K-1 (Form 1065) Partner's Share of I / box_17_amt_items |
