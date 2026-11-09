from inventory import add_item, total_quantity


def test_1():
    items = add_item("a", 2)
    assert total_quantity(items) == 2
