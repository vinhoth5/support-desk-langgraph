"""Fernhill Nursery: a made-up plant shop.

Every product, order, courier and customer in this file is invented sample
data. The functions at the bottom are the only way the agent can learn
anything about the shop, which is what makes its answers checkable.
"""

from __future__ import annotations

from datetime import date, timedelta

CATALOGUE = [
    {"sku": "FH-101", "name": "Monstera Deliciosa", "price": 899, "in_stock": True,
     "tags": ["indoor", "large", "monstera"]},
    {"sku": "FH-102", "name": "Snake Plant", "price": 349, "in_stock": True,
     "tags": ["indoor", "low light", "beginner", "snake"]},
    {"sku": "FH-103", "name": "Fiddle Leaf Fig", "price": 1499, "in_stock": False,
     "tags": ["indoor", "large", "fig", "fiddle"]},
    {"sku": "FH-104", "name": "Peace Lily", "price": 449, "in_stock": True,
     "tags": ["indoor", "flowering", "lily"]},
    {"sku": "FH-105", "name": "Jade Plant", "price": 299, "in_stock": True,
     "tags": ["succulent", "beginner", "jade"]},
    {"sku": "FH-201", "name": "Terracotta Pot Set", "price": 599, "in_stock": True,
     "tags": ["pot", "pots", "terracotta"]},
]

ORDERS = {
    "FH5001": {"customer": "anika", "items": ["Monstera Deliciosa"], "status": "out for delivery",
               "courier": "Northline Express", "last_scan": "reached the local hub", "pincode": "600042"},
    "FH5002": {"customer": "anika", "items": ["Snake Plant", "Terracotta Pot Set"], "status": "delivered",
               "courier": "Northline Express", "last_scan": "handed to the customer", "pincode": "600042"},
    "FH5003": {"customer": "rahul", "items": ["Peace Lily"], "status": "packed",
               "courier": "Bluebird Couriers", "last_scan": "waiting for pickup", "pincode": "560034"},
}

# Delivery days by the first three digits of the pincode.
DELIVERY_DAYS = {"600": 1, "560": 2, "400": 3, "110": 4}


def find_order(order_id: str, customer: str) -> dict | None:
    """Return an order only if it belongs to the customer who is asking."""
    order = ORDERS.get(order_id.upper())
    if order is None or order["customer"] != customer:
        return None
    return {"kind": "order", "order_id": order_id.upper(), **order}


def search_catalogue(query: str, limit: int = 3) -> list[dict]:
    """Match products by name or tag. Plain word overlap is enough for six items."""
    words = {w.strip("?.,!").lower() for w in query.split()}
    scored = []
    for item in CATALOGUE:
        name_words = set(item["name"].lower().split())
        score = 2 * len(words & name_words) + len(words & set(item["tags"]))
        if score:
            scored.append((score, item))
    if not scored:
        return []
    # Keep only the best matches, so "jade plant" does not drag in every other plant.
    best = max(score for score, _ in scored)
    return [{"kind": "product", **item} for score, item in scored if score == best][:limit]


def delivery_estimate(pincode: str, today: date) -> dict | None:
    """Estimate a delivery date, or return None when the area is not covered."""
    days = DELIVERY_DAYS.get(pincode[:3])
    if days is None:
        return None
    arrives = today + timedelta(days=days)
    return {"kind": "delivery", "pincode": pincode, "days": days,
            "date": f"{arrives.day} {arrives:%b}"}


def product_names() -> list[str]:
    return [item["name"] for item in CATALOGUE]
