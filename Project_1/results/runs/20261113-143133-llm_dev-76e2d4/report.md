# Field report: llm_dev

307 documents, 259 groups, 12562 fields. Outcomes: correct=3618, wrong=1287, hallucinated=334, missed=1353, true_null=5970.
Non-null predictions: 5239, precision 69.1%, Wilson-95 error upper bound 32.2%.

## Leave-one-group-out whitelist

Parameters: {"min_n": 3, "min_groups": 1, "evidence": "grounded_text", "conf": 0.0}. Booked **375** values, **0** wrong (Wilson-95 error upper bound 1.0%), 2 families, 15 groups. Net saving: E=20: +2.99%, E=100: +2.99%, E=500: +2.99%.

| evidence | min_n | min_groups | booked | wrong | wilson95 err upper | families | net E=20 | net E=100 | net E=500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| grounded_text | 3 | 1 | 375 | 0 | 1.0% | 2 | +2.99% | +2.99% | +2.99% |
| grounded_text | 5 | 1 | 359 | 0 | 1.1% | 1 | +2.86% | +2.86% | +2.86% |
| grounded_text | 10 | 1 | 352 | 0 | 1.1% | 1 | +2.80% | +2.80% | +2.80% |
| grounded_text | 20 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| grounded_text | 3 | 3 | 375 | 0 | 1.0% | 2 | +2.99% | +2.99% | +2.99% |
| grounded_text | 5 | 3 | 359 | 0 | 1.1% | 1 | +2.86% | +2.86% | +2.86% |
| grounded_text | 10 | 3 | 352 | 0 | 1.1% | 1 | +2.80% | +2.80% | +2.80% |
| grounded_text | 20 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 3 | 1 | 1697 | 29 | 2.4% | 8 | +8.89% | -9.58% | -101.92% |
| none | 5 | 1 | 1294 | 21 | 2.5% | 4 | +6.96% | -6.42% | -73.28% |
| none | 10 | 1 | 696 | 9 | 2.4% | 2 | +4.11% | -1.62% | -30.28% |
| none | 20 | 1 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |
| none | 3 | 3 | 1685 | 29 | 2.5% | 7 | +8.80% | -9.67% | -102.01% |
| none | 5 | 3 | 1294 | 21 | 2.5% | 4 | +6.96% | -6.42% | -73.28% |
| none | 10 | 3 | 696 | 9 | 2.4% | 2 | +4.11% | -1.62% | -30.28% |
| none | 20 | 3 | 0 | 0 | n/a | 0 | +0.00% | +0.00% | +0.00% |

## Missed savings (correct values not booked, whitelist parameters above)

3243 correct values were not booked.

| reason | fields |
|---|---:|
| no_evidence | 2314 |
| cell_has_errors | 579 |
| cell_too_small | 350 |

| family | reasons |
|---|---|
| cuad | {"cell_has_errors": 577, "no_evidence": 21} |
| RRCH9Extraction | {"no_evidence": 503} |
| RRC2AExtraction | {"no_evidence": 401} |
| Form W-2 Wage and Tax Statement (2020) | {"no_evidence": 330} |
| RRCP18Extraction | {"no_evidence": 325} |
| RRCH12Extraction | {"no_evidence": 311} |
| RRCW14ReviewExtraction | {"no_evidence": 105, "cell_too_small": 22} |
| Form 1099-B Proceeds From Broker and Barter E | {"cell_too_small": 61, "no_evidence": 58} |
| RRCW1Extraction | {"no_evidence": 52, "cell_too_small": 39} |
| Schedule K-1 (Form 1065) Partner's Share of I | {"no_evidence": 63, "cell_too_small": 10} |
| Schedule K-1 (Form 1120S) Shareholder's Share | {"no_evidence": 36, "cell_too_small": 22} |
| ClosingDisclosureTRID | {"cell_too_small": 39} |
| CCCMarketValuationReport | {"cell_too_small": 32, "no_evidence": 6} |
| UtilityBill | {"cell_too_small": 30, "no_evidence": 6} |
| MitchellVehicleValuationReport | {"no_evidence": 17, "cell_too_small": 10} |
| PurchaseOrder | {"no_evidence": 11, "cell_too_small": 11} |
| stem:nport | {"cell_too_small": 12, "no_evidence": 9} |
| stem:13f | {"cell_too_small": 12, "no_evidence": 4} |
| stem:mcdonalds_receipt | {"no_evidence": 14} |
| Product Spec Sheet / Datasheet — rated specif | {"no_evidence": 7, "cell_too_small": 5} |
| stem:golden_corral | {"no_evidence": 12} |
| stem:sched_i | {"no_evidence": 7, "cell_too_small": 4} |
| RRCH5Extraction | {"no_evidence": 5, "cell_too_small": 4, "cell_has_errors": 2} |
| stem:stephenville_axon | {"cell_too_small": 6, "no_evidence": 4} |
| stem:grafton_isotrope | {"cell_too_small": 6, "no_evidence": 3} |

## Precision tables (non-null predictions only)

### source / kind / grounded_text

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 181 | 176 | 5 | 0 | 97.2% | 6.3% | extractbench / number / False |
| 65 | 52 | 13 | 0 | 80.0% | 31.3% | extractbench / number / True |
| 77 | 21 | 49 | 7 | 27.3% | 81.4% | cuad / span / False |
| 853 | 794 | 59 | 0 | 93.1% | 8.8% | extractbench / boolean / False |
| 75 | 7 | 68 | 0 | 9.3% | 95.4% | extractbench / json / True |
| 738 | 668 | 64 | 6 | 90.5% | 11.8% | extractbench / string / True |
| 156 | 44 | 105 | 7 | 28.2% | 78.3% | extractbench / json / False |
| 1517 | 1279 | 173 | 65 | 84.3% | 17.6% | extractbench / string / False |
| 1577 | 577 | 751 | 249 | 36.6% | 65.8% | cuad / span / True |

### route

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 221 | 131 | 86 | 4 | 59.3% | 47.3% | text_damaged |
| 2131 | 1918 | 202 | 11 | 90.0% | 11.3% | no_text |
| 1233 | 971 | 199 | 63 | 78.8% | 23.6% | text_ok |
| 1654 | 598 | 800 | 256 | 36.2% | 66.1% | cuad_text |

### confidence written to preds (rounded)

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 8 | 7 | 1 | 0 | 87.5% | 47.1% | 0.49 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.38 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.60 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.92 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.35 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.30 |
| 1 | 0 | 1 | 0 | 0.0% | 100.0% | 0.40 |
| 5 | 1 | 4 | 0 | 20.0% | 96.4% | 0.42 |
| 6 | 0 | 2 | 4 | 0.0% | 100.0% | 0.75 |
| 14 | 4 | 10 | 0 | 28.6% | 88.3% | 0.45 |
| 11 | 1 | 8 | 2 | 9.1% | 98.4% | 0.70 |
| 51 | 38 | 13 | 0 | 74.5% | 38.9% | 0.50 |
| 79 | 61 | 17 | 1 | 77.2% | 33.2% | 0.98 |
| 50 | 22 | 28 | 0 | 44.0% | 68.8% | 0.47 |
| 670 | 641 | 28 | 1 | 95.7% | 6.1% | 0.99 |
| 39 | 9 | 19 | 11 | 23.1% | 87.4% | 0.80 |
| 142 | 25 | 65 | 52 | 17.6% | 87.8% | 0.85 |
| 358 | 92 | 174 | 92 | 25.7% | 78.6% | 0.90 |
| 2300 | 1990 | 269 | 41 | 86.5% | 14.9% | 1.00 |
| 1500 | 727 | 643 | 130 | 48.5% | 54.1% | 0.95 |

### family / field (grounded only, n >= 3), safest first

| n | correct | wrong | halluc | precision | wilson95 err upper | key |
|---:|---:|---:|---:|---:|---:|---|
| 14 | 14 | 0 | 0 | 100.0% | 21.5% | Form 1099-B Proceeds From Broker and Barter E / recipient_name |
| 13 | 13 | 0 | 0 | 100.0% | 22.8% | Form 1099-B Proceeds From Broker and Barter E / payer_federal_id |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / uic_no |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / filing_no |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / submittal_date |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / version |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / evaluation |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / test_status |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / preparer |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / preparer_phone |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / preparer_email |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / operator_name |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / operator_no |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / operator_address_line_1 |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / operator_city |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / operator_state |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / operator_postal_code |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / api |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / injection_well |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / district |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / lease_no |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / well_no |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / lease_name |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / field_number |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / field_name |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / county |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / reason_for |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / date_test_performed |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / retest |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / packer_make_model |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / depth_packer |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / well_status |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / test_witnessed_by_rrc |
| 11 | 11 | 0 | 0 | 100.0% | 25.9% | RRCH5Extraction / annulus_fluid_description |
| 7 | 7 | 0 | 0 | 100.0% | 35.4% | RRCH5Extraction / injection_fluid_description |
| 4 | 4 | 0 | 0 | 100.0% | 49.0% | stem:sched_i / filer_name |
| 4 | 4 | 0 | 0 | 100.0% | 49.0% | stem:sched_i / tax_period_end_date |
| 4 | 4 | 0 | 0 | 100.0% | 49.0% | stem:sched_i / total_other_org_count |
| 4 | 4 | 0 | 0 | 100.0% | 49.0% | RRCH5Extraction / operator_comments_on_test |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Schedule K-1 (Form 1120S) Shareholder's Share / shareholder_stock_ownership_pct |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:13f / filing_manager_name |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:13f / report_type |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:13f / table_entry_total |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:13f / table_value_total_usd |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | UtilityBill / utility_provider |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | UtilityBill / account_number |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | UtilityBill / customer_name |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | UtilityBill / service_address |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | UtilityBill / billing_period_start |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | UtilityBill / billing_period_end |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | UtilityBill / payment_due_date |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:sched_i / total_501c3_org_count |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | Product Spec Sheet / Datasheet — rated specif / product_title |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | PurchaseOrder / buyer_contact |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:nport / filer_name |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:nport / series_id |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:nport / series_name |
| 3 | 3 | 0 | 0 | 100.0% | 56.2% | stem:nport / report_period_end |
| 13 | 12 | 1 | 0 | 92.3% | 33.3% | Form 1099-B Proceeds From Broker and Barter E / account_number |
| 13 | 11 | 2 | 0 | 84.6% | 42.2% | Form 1099-B Proceeds From Broker and Barter E / payer_name |
