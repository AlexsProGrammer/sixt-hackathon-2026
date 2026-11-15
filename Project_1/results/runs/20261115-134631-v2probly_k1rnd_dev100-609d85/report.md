# Field report: v2probly_k1rnd_dev100

65 documents, 59 groups, 2704 fields. Outcomes: correct=335, wrong=206, hallucinated=91, missed=732, true_null=1340.
Non-null predictions: 632, precision 53.0%, Wilson-95 error upper bound 50.9%.

## Leave-one-group-out whitelist

Parameters: {"min_n": 3, "min_groups": 1, "evidence": "grounded_text", "conf": 0.0}. Booked **1** values, **1** wrong (Wilson-95 error upper bound 100.0%), 1 families, 1 groups. Net saving: E=20: -0.70%, E=100: -3.66%, E=500: -18.45%.

| evidence | min_n | min_groups | booked | wrong | wilson95 err upper | families | net E=20 | net E=100 | net E=500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| grounded_text | 3 | 1 | 1 | 1 | 100.0% | 1 | -0.70% | -3.66% | -18.45% |
| grounded_text | 5 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 10 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 20 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 3 | 3 | 1 | 1 | 100.0% | 1 | -0.70% | -3.66% | -18.45% |
| grounded_text | 5 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 10 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 20 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 3 | 1 | 1 | 1 | 100.0% | 1 | -0.70% | -3.66% | -18.45% |
| none | 5 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 10 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 20 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 3 | 3 | 1 | 1 | 100.0% | 1 | -0.70% | -3.66% | -18.45% |
| none | 5 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 10 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 20 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |

## Missed savings (correct values not booked, whitelist parameters above)

335 correct values were not booked.

| reason | fields |
|---|---:|
| cell_has_errors | 176 |
| cell_too_small | 159 |

| family | reasons |
|---|---|
| cuad | {"cell_has_errors": 176, "cell_too_small": 2} |
| RRCH5Extraction | {"cell_too_small": 69} |
| ClosingDisclosureTRID | {"cell_too_small": 42} |
| Form 1099-B Proceeds From Broker and Barter E | {"cell_too_small": 13} |
| UtilityBill | {"cell_too_small": 9} |
| PurchaseOrder | {"cell_too_small": 6} |
| stem:sched_i | {"cell_too_small": 5} |
| stem:13f | {"cell_too_small": 4} |
| stem:nport | {"cell_too_small": 4} |
| Schedule K-1 (Form 1120S) Shareholder's Share | {"cell_too_small": 3} |
| Schedule K-1 (Form 1065) Partner's Share of I | {"cell_too_small": 2} |

## Precision tables (non-null predictions only)

### source / kind / grounded_text

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 12 | 11 | 0 | 1 | 91.7% | 35.4% | extractbench / number / True |
| 139 | 137 | 2 | 0 | 98.6% | 5.1% | extractbench / string / True |
| 14 | 9 | 5 | 0 | 64.3% | 61.2% | extractbench / json / True |
| 467 | 178 | 199 | 90 | 38.1% | 66.2% | cuad / span / True |

### route

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 137 | 135 | 2 | 0 | 98.5% | 5.2% | pdf_text_good |
| 28 | 22 | 5 | 1 | 78.6% | 39.5% | pdf_text_damaged |
| 467 | 178 | 199 | 90 | 38.1% | 66.2% | cuad |

### confidence written to preds (rounded)

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 72 | 72 | 0 | 0 | 100.0% | 5.1% | 0.99 |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | 0.96 |
| 4 | 3 | 1 | 0 | 75.0% | 69.9% | 0.92 |
| 3 | 2 | 1 | 0 | 66.7% | 79.2% | 0.93 |
| 1 | 0 | 0 | 1 | 0.0% | 100.0% | 0.78 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.68 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.58 |
| 1 | 0 | 0 | 1 | 0.0% | 100.0% | 0.25 |
| 37 | 35 | 2 | 0 | 94.6% | 17.7% | 0.98 |
| 4 | 2 | 1 | 1 | 50.0% | 85.0% | 0.82 |
| 3 | 1 | 1 | 1 | 33.3% | 93.9% | 0.72 |
| 2 | 0 | 0 | 2 | 0.0% | 100.0% | 0.30 |
| 2 | 0 | 2 | 0 | 0.0% | 100.0% | 0.94 |
| 2 | 0 | 0 | 2 | 0.0% | 100.0% | 0.35 |
| 36 | 33 | 3 | 0 | 91.7% | 21.8% | 0.97 |
| 3 | 0 | 2 | 1 | 0.0% | 100.0% | 0.45 |
| 4 | 0 | 1 | 3 | 0.0% | 100.0% | 0.40 |
| 8 | 3 | 3 | 2 | 37.5% | 86.3% | 0.88 |
| 5 | 0 | 3 | 2 | 0.0% | 100.0% | 0.65 |
| 13 | 7 | 2 | 4 | 53.8% | 70.9% | 0.75 |
| 29 | 14 | 10 | 5 | 48.3% | 68.6% | 0.80 |
| 23 | 8 | 6 | 9 | 34.8% | 81.2% | 0.70 |
| 21 | 3 | 7 | 11 | 14.3% | 95.0% | 0.55 |
| 30 | 6 | 8 | 16 | 20.0% | 90.5% | 0.60 |
| 30 | 5 | 15 | 10 | 16.7% | 92.7% | 0.50 |
| 57 | 15 | 29 | 13 | 26.3% | 83.4% | 0.85 |
| 120 | 75 | 45 | 0 | 62.5% | 46.4% | 0.95 |
| 117 | 48 | 62 | 7 | 41.0% | 67.5% | 0.90 |

### family / field (grounded only, n >= 3), safest first

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Form 1099-B Proceeds From Broker and Barter E / payer_federal_id |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Form 1099-B Proceeds From Broker and Barter E / recipient_name |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Form 1099-B Proceeds From Broker and Barter E / recipient_tax_id |
| 4 | 3 | 0 | 1 | 75.0% | 69.9% | cuad / No-Solicit Of Employees |
| 3 | 2 | 1 | 0 | 66.7% | 79.2% | Form 1099-B Proceeds From Broker and Barter E / account_number |
| 4 | 2 | 1 | 1 | 50.0% | 85.0% | cuad / Joint Ip Ownership |
| 4 | 2 | 2 | 0 | 50.0% | 85.0% | cuad / Irrevocable Or Perpetual License |
| 4 | 2 | 2 | 0 | 50.0% | 85.0% | cuad / No-Solicit Of Customers |
| 3 | 1 | 1 | 1 | 33.3% | 93.9% | cuad / Liquidated Damages |
| 3 | 1 | 1 | 1 | 33.3% | 93.9% | cuad / Non-Disparagement |
| 5 | 2 | 1 | 2 | 40.0% | 88.2% | cuad / Covenant Not To Sue |
| 3 | 0 | 0 | 3 | 0.0% | 100.0% | cuad / Affiliate License-Licensor |
| 3 | 0 | 3 | 0 | 0.0% | 100.0% | cuad / Warranty Duration |
| 6 | 2 | 3 | 1 | 33.3% | 90.3% | cuad / Rofr/Rofo/Rofn |
| 8 | 3 | 1 | 4 | 37.5% | 86.3% | cuad / Post-Termination Services |
| 6 | 1 | 0 | 5 | 16.7% | 97.0% | cuad / Affiliate License-Licensee |
| 33 | 27 | 5 | 1 | 81.8% | 34.4% | cuad / Agreement Date |
| 19 | 13 | 1 | 5 | 68.4% | 54.0% | cuad / Termination For Convenience |
| 11 | 5 | 6 | 0 | 45.5% | 78.7% | cuad / Insurance |
| 8 | 2 | 5 | 1 | 25.0% | 92.9% | cuad / Revenue/Profit Sharing |
| 6 | 0 | 4 | 2 | 0.0% | 100.0% | cuad / Uncapped Liability |
| 13 | 6 | 6 | 1 | 46.2% | 76.8% | cuad / Cap On Liability |
| 12 | 5 | 2 | 5 | 41.7% | 80.7% | cuad / Competitive Restriction Exception |
| 11 | 4 | 5 | 2 | 36.4% | 84.8% | cuad / Non-Compete |
| 36 | 28 | 8 | 0 | 77.8% | 38.1% | cuad / Document Name |
| 16 | 8 | 5 | 3 | 50.0% | 72.0% | cuad / License Grant |
| 12 | 4 | 3 | 5 | 33.3% | 86.2% | cuad / Non-Transferable License |
| 12 | 4 | 7 | 1 | 33.3% | 86.2% | cuad / Minimum Commitment |
| 25 | 16 | 8 | 1 | 64.0% | 55.5% | cuad / Effective Date |
| 13 | 4 | 9 | 0 | 30.8% | 87.3% | cuad / Audit Rights |
| 12 | 3 | 3 | 6 | 25.0% | 91.1% | cuad / Change Of Control |
| 9 | 0 | 8 | 1 | 0.0% | 100.0% | cuad / Notice Period To Terminate Renewal |
| 9 | 0 | 9 | 0 | 0.0% | 100.0% | cuad / Expiration Date |
| 23 | 13 | 10 | 0 | 56.5% | 63.2% | cuad / Anti-Assignment |
| 10 | 0 | 2 | 8 | 0.0% | 100.0% | cuad / Volume Restriction |
| 14 | 3 | 4 | 7 | 21.4% | 92.4% | cuad / Ip Ownership Assignment |
| 11 | 0 | 11 | 0 | 0.0% | 100.0% | cuad / Renewal Term |
| 16 | 3 | 5 | 8 | 18.8% | 93.4% | cuad / Exclusivity |
| 13 | 0 | 1 | 12 | 0.0% | 100.0% | cuad / Price Restrictions |
| 33 | 5 | 28 | 0 | 15.2% | 93.3% | cuad / Governing Law |
| 35 | 6 | 29 | 0 | 17.1% | 91.9% | cuad / Parties |
