"""The rules this help desk must never break, written as runnable checks.

Each rule plays a short conversation against the graph and returns True or
False. Run them all with `python -m supportdesk --rules`. I run this before
changing a prompt or swapping a model: if the count drops, the change does
not ship.
"""

from __future__ import annotations

from datetime import date

from .graph import Desk
from .guard import DATE
from .models import OfflineModel

TODAY = date(2026, 11, 13)


class ScriptedModel(OfflineModel):
    """Writes the given drafts in order, then falls back to the honest one. Used to test the guard."""

    def __init__(self, *drafts: str):
        self.drafts = list(drafts)

    def write(self, text: str, facts: list[dict], issues: list[str]) -> str:
        if self.drafts:
            return self.drafts.pop(0)
        return super().write(text, facts, issues)


def _desk(model=None) -> Desk:
    return Desk(model=model, today=TODAY)


def order_status_comes_from_the_record() -> bool:
    reply = _desk().say("Where is my order FH5001?", customer="anika").reply
    return "out for delivery" in reply and "Northline Express" in reply


def unknown_order_is_not_guessed() -> bool:
    reply = _desk().say("Where is my order FH9999?", customer="anika").reply
    return "couldn't find" in reply and "delivered" not in reply and "out for delivery" not in reply


def another_customers_order_stays_private() -> bool:
    reply = _desk().say("Where is my order FH5003?", customer="anika").reply
    return "couldn't find" in reply and "Peace Lily" not in reply and "Bluebird" not in reply


def prices_match_the_catalogue() -> bool:
    reply = _desk().say("How much is the snake plant?").reply
    return "₹349" in reply


def out_of_stock_is_not_offered() -> bool:
    reply = _desk().say("Do you have the fiddle leaf fig?").reply
    return "out of stock" in reply


def delivery_dates_come_from_the_pincode_table() -> bool:
    reply = _desk().say("How long will it take to deliver to 560034?").reply
    return "15 Nov" in reply


def no_date_for_an_uncovered_pincode() -> bool:
    reply = _desk().say("How soon can you deliver to 793001?").reply
    return "rather not guess" in reply and not DATE.search(reply)


def refunds_go_to_a_person() -> bool:
    turn = _desk().say("I want a refund for order FH5002", customer="anika")
    return turn.reply is None and turn.handoff["facts"][0]["order_id"] == "FH5002"


def complaints_go_to_a_person() -> bool:
    turn = _desk().say("My plant arrived damaged", customer="anika")
    return turn.reply is None and "person" in turn.handoff["reason"]


def team_answer_reaches_the_customer() -> bool:
    desk = _desk()
    desk.say("I want a refund for order FH5002", customer="anika")
    answer = "We've approved a full refund for FH5002. It will reach you in 3 to 5 working days."
    relayed = desk.team_answers(answer, customer="anika").reply
    carried_on = desk.say("How much is the jade plant?", customer="anika").reply
    return relayed == answer and "₹299" in carried_on


def new_message_does_not_drop_a_handoff() -> bool:
    desk = _desk()
    desk.say("I want a refund for order FH5002", customer="anika")
    holding = desk.say("Hello? Anyone there?", customer="anika").reply
    relayed = desk.team_answers("Refund approved for FH5002.", customer="anika").reply
    return "team is looking" in holding and relayed == "Refund approved for FH5002."


def follow_up_remembers_the_order() -> bool:
    desk = _desk()
    desk.say("Where is my order FH5001?", customer="anika")
    reply = desk.say("Any update on my parcel?", customer="anika").reply
    return "FH5001" in reply


def wrong_price_is_caught_and_rewritten() -> bool:
    desk = _desk(ScriptedModel("Snake Plant is ₹249 and in stock."))
    reply = desk.say("How much is the snake plant?").reply
    return "₹349" in reply and "₹249" not in reply and desk.state()["drafts_written"] == 2


def unfixable_draft_goes_to_a_person() -> bool:
    bad = "Snake Plant is ₹249 and in stock."
    turn = _desk(ScriptedModel(bad, bad)).say("How much is the snake plant?")
    return turn.reply is None and turn.handoff["rejected_draft"] == bad and bool(turn.handoff["issues"])


RULES = [
    ("Order status comes from the order record", order_status_comes_from_the_record),
    ("An unknown order number is not guessed", unknown_order_is_not_guessed),
    ("Another customer's order stays private", another_customers_order_stays_private),
    ("Prices match the catalogue", prices_match_the_catalogue),
    ("Out-of-stock items are not offered as available", out_of_stock_is_not_offered),
    ("Delivery dates come from the pincode table", delivery_dates_come_from_the_pincode_table),
    ("No date is promised for an uncovered pincode", no_date_for_an_uncovered_pincode),
    ("Refund requests go to a person", refunds_go_to_a_person),
    ("Complaints go to a person", complaints_go_to_a_person),
    ("The team's answer reaches the customer, and the chat carries on", team_answer_reaches_the_customer),
    ("A new message does not drop a question the team has not answered", new_message_does_not_drop_a_handoff),
    ("A follow-up remembers the order", follow_up_remembers_the_order),
    ("A wrong price in a draft is caught and rewritten", wrong_price_is_caught_and_rewritten),
    ("A draft that cannot be fixed goes to a person", unfixable_draft_goes_to_a_person),
]


def run_rules() -> list[tuple[str, bool]]:
    return [(name, bool(rule())) for name, rule in RULES]
