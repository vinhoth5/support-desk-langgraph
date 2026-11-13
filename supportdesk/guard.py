"""Checks a drafted reply against the facts the agent actually looked up.

A language model will happily state a price or a delivery date it never saw.
The guard does not try to judge tone or helpfulness. It answers one narrow
question: does this reply say anything specific that the facts do not support?
"""

from __future__ import annotations

import re

from .shop import product_names

PRICE = re.compile(r"₹\s?([\d,]+)")
ORDER_ID = re.compile(r"\bFH\d{4}\b", re.IGNORECASE)
DATE = re.compile(r"\b(\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))\b")

# Commitments only a person on the team is allowed to make.
PROMISES = ("refund", "replacement", "guarantee", "compensat", "free of charge")


def check_reply(draft: str, facts: list[dict]) -> list[str]:
    """Return a list of problems. An empty list means the reply can go out."""
    issues: list[str] = []
    products = [f for f in facts if f["kind"] == "product"]
    orders = [f for f in facts if f["kind"] == "order"]
    deliveries = [f for f in facts if f["kind"] == "delivery"]
    text = draft.lower()

    known_prices = {f["price"] for f in products}
    for raw in PRICE.findall(draft):
        if int(raw.replace(",", "")) not in known_prices:
            issues.append(f"Price ₹{raw} does not match any product that was looked up.")

    known_orders = {f["order_id"] for f in orders}
    for order_id in ORDER_ID.findall(draft):
        if order_id.upper() not in known_orders:
            issues.append(f"Order {order_id.upper()} was mentioned but never looked up.")

    known_dates = {f["date"] for f in deliveries}
    for day in DATE.findall(draft):
        if day not in known_dates:
            issues.append(f"Delivery date {day} did not come from the delivery estimate.")

    looked_up = {f["name"] for f in products} | {name for f in orders for name in f["items"]}
    for name in product_names():
        if name.lower() in text and name not in looked_up:
            issues.append(f"{name} was mentioned but never looked up.")

    for product in products:
        name = product["name"].lower()
        if not product["in_stock"] and name in text:
            sentence = _sentence_with(text, name)
            if "in stock" in sentence and "out of stock" not in sentence and "not in stock" not in sentence:
                issues.append(f"{product['name']} is out of stock but the reply says it is available.")

    for word in PROMISES:
        if word in text:
            issues.append(f"The reply makes a commitment ('{word}') that only the team can make.")
            break

    return issues


def _sentence_with(text: str, phrase: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if phrase in sentence:
            return sentence
    return text
