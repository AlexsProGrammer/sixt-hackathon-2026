"""Project 5 quickstart: solve toy question DEMO001 with code, then write the answer CSV format.

The pattern: ordinary code does the calculation (no double-counting), the output is question_id,answer.
"""
from pathlib import Path

import pandas as pd

ex = Path(__file__).resolve().parent / "examples"
orders = pd.read_csv(ex / "orders.csv")
payments = pd.read_csv(ex / "payments.csv")

# DEMO001: valid = completed or shipped AND at least one settled payment (each order counted once)
settled = set(payments.loc[payments.status == "settled", "order_id"])
answer = orders[orders.status.isin(["completed", "shipped"]) & orders.order_id.isin(settled)].order_id.nunique()

pd.DataFrame({"question_id": ["DEMO001"], "answer": [answer]}).to_csv("quickstart_answers.csv", index=False)
expected = pd.read_csv(ex / "demo_answers.csv", dtype=str).set_index("question_id").loc["DEMO001", "answer"]
print(f"DEMO001 = {answer} (expected {expected}) ->", "OK" if str(answer) == str(expected) else "MISMATCH")
print("Wrote quickstart_answers.csv (columns: question_id,answer)")
