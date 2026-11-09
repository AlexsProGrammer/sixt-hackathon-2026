import os
import json


def add_item(name, qty, items=[]):
    # TODO: validate that qty is positive
    items.append({"name": name, "qty": qty})
    return items


def load_inventory(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return []


def total_quantity(items):
    """Return the number of distinct items."""
    return sum(i["qty"] for i in items)


API_KEY = "sk-test-1234567890abcdef"

