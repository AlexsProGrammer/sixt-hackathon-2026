# Three toy examples

These miniature examples are invented for preparation. They are not live competition questions or private reference answers. All eligibility conditions not shown are assumed satisfied; the full competition rules remain authoritative for the released datasets.

## DEMO001: Filter records without double-counting

**Question:** How many valid orders are there? For this example, a valid order must be completed or shipped and have at least one settled payment.

`orders.csv`:

| order_id | status | payment_status |
|---|---|---|
| A | completed | paid |
| B | cancelled | paid |
| C | shipped | paid |

`payments.csv`:

| payment_id | order_id | status |
|---|---|---|
| p1 | A | settled |
| p2 | A | settled |
| p3 | B | settled |
| p4 | C | failed |

**Answer: `1`.** Order A qualifies once despite having two settled payments. B is cancelled. C has no settled payment. Use the payments to establish eligibility, rather than counting joined payment rows as separate orders.

## DEMO002: Apply discounts and the correct exchange rates

**Question:** What is net revenue in EUR for this valid single-line order?

| Input | Value |
|---|---:|
| Quantity | 2 |
| Unit price, USD | 50 |
| Total line discount, USD | 10 |
| Total order discount, USD | 5 |
| Order-month EUR per USD | 0.90 |
| Eligible approved refund, USD | 10 |
| Refund-month EUR per USD | 0.92 |

**Answer: `67.30`.**

```text
Discounted amount, USD = 2 × 50 - 10 - 5 = 85
Discounted amount, EUR = 85 × 0.90 = 76.50
Refund, EUR = 10 × 0.92 = 9.20
Net revenue, EUR = 76.50 - 9.20 = 67.30
```

The order has only one item line, so that line receives the entire order discount. Use the exchange rate for each event's month, and round only the final answer.

## DEMO003: Respect a strict threshold

**Question:** How many replenishment units are suggested? Reorder only when end stock is strictly below the reorder point; if triggered, replenish to target stock.

Opening stock is 50. The reorder point is 40 and the target is 70.

| Movement | Units | Status | Timing |
|---|---:|---|---|
| Receipt | +20 | posted | After stocktake, by reference time |
| Sale issue | -35 | posted | After stocktake, by reference time |
| Return restock | +5 | posted | After stocktake, by reference time |
| Adjustment | +100 | draft | Before reference time |
| Receipt | +10 | posted | After reference time |

**Answer: `0`.** End stock is `50 + 20 - 35 + 5 = 40`. Exclude draft and future movements. Equality with the reorder point does not trigger an order. Do not add a receipt twice if it already appears in the movement ledger.

## Example answer file

The complete file is [demo_answers.csv](demo_answers.csv):

```csv
question_id,answer
DEMO001,1
DEMO002,67.30
DEMO003,0
```

The teaching tables are also provided as CSV files. They are independent toy data with simplified schemas, not fragments of the live dataset.
