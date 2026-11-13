from supportdesk.guard import check_reply

SNAKE = {"kind": "product", "sku": "FH-102", "name": "Snake Plant", "price": 349, "in_stock": True, "tags": []}
FIG = {"kind": "product", "sku": "FH-103", "name": "Fiddle Leaf Fig", "price": 1499, "in_stock": False, "tags": []}
ORDER = {"kind": "order", "order_id": "FH5001", "items": ["Monstera Deliciosa"], "status": "packed",
         "courier": "Northline Express", "last_scan": "waiting for pickup", "pincode": "600042", "customer": "anika"}
DELIVERY = {"kind": "delivery", "pincode": "560034", "days": 2, "date": "15 Nov"}


def test_a_reply_built_from_the_facts_passes():
    assert check_reply("Snake Plant is ₹349 and in stock.", [SNAKE]) == []
    assert check_reply("Order FH5001 (Monstera Deliciosa) is packed.", [ORDER]) == []
    assert check_reply("It should arrive around 15 Nov.", [DELIVERY]) == []


def test_a_price_that_was_never_looked_up_is_flagged():
    assert check_reply("Snake Plant is ₹249.", [SNAKE])


def test_a_price_with_a_comma_is_read_correctly():
    assert check_reply("Fiddle Leaf Fig is ₹1,499 and out of stock right now.", [FIG]) == []


def test_an_order_that_was_never_looked_up_is_flagged():
    assert check_reply("Order FH5003 is on its way.", [ORDER])


def test_a_made_up_delivery_date_is_flagged():
    assert check_reply("It will arrive on 14 Nov.", [DELIVERY])


def test_a_product_that_was_never_looked_up_is_flagged():
    assert check_reply("You might also like the Peace Lily.", [SNAKE])


def test_out_of_stock_cannot_be_called_available():
    assert check_reply("Fiddle Leaf Fig is ₹1,499 and in stock.", [FIG])


def test_only_the_team_can_promise_a_refund():
    assert check_reply("I've arranged a refund for you.", [ORDER])


def test_a_plain_reply_with_no_specifics_passes():
    assert check_reply("Which six-digit pincode should I check the delivery time for?", []) == []
