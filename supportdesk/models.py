"""The two jobs the graph gives to a model, and two ways of doing them.

The graph never talks to a model directly. It asks for an Understanding of the
customer's message and, later, for a reply written from a set of facts. That
keeps the graph testable: OfflineModel needs no API key and always gives the
same answer, while ChatModel hands the same two jobs to any LangChain chat
model.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

INTENTS = ("order_status", "delivery", "product", "refund", "complaint", "greeting", "unknown")
GREETING = re.compile(r"\b(hi|hello|hey|good morning|good evening)\b")


@dataclass
class Understanding:
    intent: str = "unknown"
    order_id: str | None = None
    pincode: str | None = None
    product_query: str | None = None


class Model(Protocol):
    def understand(self, text: str, known_order: str | None) -> Understanding: ...

    def write(self, text: str, facts: list[dict], issues: list[str]) -> str: ...


class OfflineModel:
    """Keyword rules and templates. Good enough to run and test the graph."""

    def understand(self, text: str, known_order: str | None) -> Understanding:
        lower = text.lower()
        order = re.search(r"\bFH\d{4}\b", text, re.IGNORECASE)
        pincode = re.search(r"\b\d{6}\b", text)
        found = Understanding(
            order_id=order.group(0).upper() if order else None,
            pincode=pincode.group(0) if pincode else None,
        )
        if _any(lower, "refund", "money back", "cancel"):
            found.intent = "refund"
        elif _any(lower, "damaged", "broken", "dead", "wilted", "complain", "worst", "terrible"):
            found.intent = "complaint"
        elif pincode and _any(lower, "deliver", "arrive", "reach", "how long", "how soon"):
            found.intent = "delivery"
        elif order or _any(lower, "where is", "track", "my order", "status", "parcel"):
            found.intent = "order_status"
        elif _any(lower, "deliver", "arrive", "how long", "how soon"):
            found.intent = "delivery"
        elif _any(lower, "price", "cost", "how much", "do you have", "stock", "looking for", "sell"):
            found.intent = "product"
            found.product_query = text
        elif GREETING.search(lower):
            found.intent = "greeting"
        return found

    def write(self, text: str, facts: list[dict], issues: list[str]) -> str:
        lines = []
        for fact in facts:
            if fact["kind"] == "order":
                lines.append(
                    f"Order {fact['order_id']} ({', '.join(fact['items'])}) is {fact['status']} "
                    f"with {fact['courier']}. The last scan says it {fact['last_scan']}."
                )
            elif fact["kind"] == "product":
                stock = "in stock" if fact["in_stock"] else "out of stock right now"
                lines.append(f"{fact['name']} is ₹{fact['price']:,} and {stock}.")
            elif fact["kind"] == "delivery":
                day = "day" if fact["days"] == 1 else "days"
                lines.append(
                    f"Delivery to {fact['pincode']} takes about {fact['days']} {day}, "
                    f"so an order placed today should arrive around {fact['date']}."
                )
            elif fact["kind"] == "missing":
                lines.append(fact["say"])
        if lines:
            return " ".join(lines)
        if GREETING.search(text.lower()):
            return "Hello, this is the Fernhill Nursery help desk. I can check an order, a price or a delivery date."
        return "I'm not sure I followed. I can check an order, a price or a delivery date. Which would you like?"


class ChatModel:
    """The same two jobs, done by a LangChain chat model."""

    def __init__(self, chat):
        self.chat = chat
        self._fallback = OfflineModel()

    @classmethod
    def from_env(cls) -> "ChatModel":
        """Build from SUPPORTDESK_MODEL, e.g. "openai:gpt-4o-mini". Needs `pip install langchain`."""
        from langchain.chat_models import init_chat_model

        return cls(init_chat_model(os.environ["SUPPORTDESK_MODEL"]))

    def understand(self, text: str, known_order: str | None) -> Understanding:
        prompt = (
            "You sort messages for a plant shop's help desk. Reply with JSON only, with the keys "
            f"intent (one of {', '.join(INTENTS)}), order_id (like FH5001, or null), "
            "pincode (six digits, or null) and product_query (what they want to buy, or null).\n"
            f"An order mentioned earlier in this conversation: {known_order or 'none'}.\n"
            f"Customer message: {text}"
        )
        try:
            data = json.loads(_json_part(self.chat.invoke(prompt).content))
            if data.get("intent") not in INTENTS:
                raise ValueError("unknown intent")
        except (ValueError, AttributeError, TypeError):
            # A model that cannot follow the format should not take the desk down.
            return self._fallback.understand(text, known_order)
        order_id = data.get("order_id") or None
        return Understanding(
            intent=data["intent"],
            order_id=order_id.upper() if order_id else None,
            pincode=data.get("pincode") or None,
            product_query=data.get("product_query") or None,
        )

    def write(self, text: str, facts: list[dict], issues: list[str]) -> str:
        prompt = (
            "You answer customers of Fernhill Nursery, a plant shop. Write a short, friendly reply.\n"
            "Use only the facts below. Never state a price, order, product or date that is not in them, "
            "and never promise a refund or replacement.\n"
            f"Facts: {json.dumps(facts, ensure_ascii=False)}\n"
            f"Customer message: {text}"
        )
        if issues:
            prompt += "\nYour last draft was rejected for these reasons, so fix them:\n- " + "\n- ".join(issues)
        return str(self.chat.invoke(prompt).content).strip()


def _any(text: str, *phrases: str) -> bool:
    return any(re.search(rf"\b{re.escape(p)}", text) for p in phrases)


def _json_part(raw: str) -> str:
    """Models often wrap JSON in prose or code fences. Take the outermost braces."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return raw[start : end + 1]
