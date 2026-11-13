"""The help desk as a LangGraph state machine.

    understand -> look_up -> draft -> check -> send
                     |          ^       |
                     |          +-------+   (rewrite when the check fails)
                     v                  v
                  ask_team <------------+   (a person takes over)
                     |
                     +-> send

Each customer conversation is one thread. The checkpointer keeps the thread's
state between messages, which is what lets a follow-up like "any update?"
work, and what lets the graph stop and wait for a person at ask_team.
"""

from dataclasses import dataclass
from datetime import date
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt

from . import shop
from .guard import check_reply
from .models import Model, OfflineModel

MAX_DRAFTS = 2
TEAM_ONLY = ("refund", "complaint")
HOLDING = (
    "Someone from our team is looking at your earlier message and will reply here. "
    "I'll pick this up as soon as they have."
)


class DeskState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    order_id: str | None  # remembered for the whole conversation
    # Everything below is rebuilt for each customer message.
    intent: str
    pincode: str | None
    product_query: str | None
    facts: list[dict]
    draft: str
    issues: list[str]
    drafts_written: int
    handoff_reason: str | None


def build_graph(model: Model | None = None, checkpointer=None):
    model = model or OfflineModel()

    def understand(state: DeskState) -> dict:
        seen = model.understand(state["messages"][-1].content, state.get("order_id"))
        return {
            "intent": seen.intent,
            "order_id": seen.order_id or state.get("order_id"),
            "pincode": seen.pincode,
            "product_query": seen.product_query,
            "facts": [],
            "draft": "",
            "issues": [],
            "drafts_written": 0,
            "handoff_reason": None,
        }

    def look_up(state: DeskState, config: RunnableConfig) -> dict:
        settings = config.get("configurable", {})
        customer = settings.get("customer", "guest")
        today = date.fromisoformat(settings["today"]) if settings.get("today") else date.today()
        intent, facts = state["intent"], []

        if intent in ("order_status", *TEAM_ONLY):
            order = shop.find_order(state["order_id"], customer) if state.get("order_id") else None
            if order:
                facts.append(order)
            elif intent == "order_status":
                facts.append(_missing(
                    "I couldn't find that order on your account. Could you check the order number? "
                    "It starts with FH and has four digits."
                ))
        elif intent == "delivery":
            if not state.get("pincode"):
                facts.append(_missing("Which six-digit pincode should I check the delivery time for?"))
            else:
                estimate = shop.delivery_estimate(state["pincode"], today)
                facts.append(estimate or _missing(
                    "I don't have a delivery estimate for that pincode yet, so I'd rather not guess a date."
                ))
        elif intent == "product":
            found = shop.search_catalogue(state.get("product_query") or "")
            facts.extend(found or [_missing(
                "I couldn't find that in our catalogue. Could you tell me the plant's name?"
            )])

        if intent in TEAM_ONLY:
            return {"facts": facts, "handoff_reason": "Refunds and complaints are decided by a person."}
        return {"facts": facts}

    def draft(state: DeskState) -> dict:
        reply = model.write(state["messages"][-1].content, state["facts"], state["issues"])
        return {"draft": reply, "drafts_written": state["drafts_written"] + 1}

    def check(state: DeskState) -> dict:
        issues = check_reply(state["draft"], state["facts"])
        if issues and state["drafts_written"] >= MAX_DRAFTS:
            return {"issues": issues, "handoff_reason": "The agent could not write a reply that matched the facts."}
        return {"issues": issues}

    def ask_team(state: DeskState) -> dict:
        # interrupt() stops the graph here and saves the thread. Nothing below
        # runs until someone resumes it with the team's answer.
        answer = interrupt({
            "reason": state["handoff_reason"],
            "customer_message": state["messages"][-1].content,
            "facts": state["facts"],
            "rejected_draft": state["draft"] or None,
            "issues": state["issues"],
        })
        # What a person on the team writes goes out as written.
        return {"draft": str(answer).strip(), "issues": []}

    def send(state: DeskState) -> dict:
        return {"messages": [AIMessage(state["draft"])]}

    def after_look_up(state: DeskState) -> str:
        return "ask_team" if state["intent"] in TEAM_ONLY else "draft"

    def after_check(state: DeskState) -> str:
        if not state["issues"]:
            return "send"
        return "draft" if state["drafts_written"] < MAX_DRAFTS else "ask_team"

    builder = StateGraph(DeskState)
    builder.add_node("understand", understand)
    builder.add_node("look_up", look_up)
    builder.add_node("draft", draft)
    builder.add_node("check", check)
    builder.add_node("ask_team", ask_team)
    builder.add_node("send", send)

    builder.add_edge(START, "understand")
    builder.add_edge("understand", "look_up")
    builder.add_conditional_edges("look_up", after_look_up, ["draft", "ask_team"])
    builder.add_edge("draft", "check")
    builder.add_conditional_edges("check", after_check, ["send", "draft", "ask_team"])
    builder.add_edge("ask_team", "send")
    builder.add_edge("send", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


def _missing(say: str) -> dict:
    """A lookup that found nothing. The wording is fixed so the agent cannot fill the gap."""
    return {"kind": "missing", "say": say}


@dataclass
class Turn:
    """What came back from one step: a reply for the customer, or a question for the team."""

    reply: str | None = None
    handoff: dict | None = None


class Desk:
    """A small wrapper so callers do not need to know LangGraph's invoke and resume calls."""

    def __init__(self, model: Model | None = None, today: date | None = None):
        self.graph = build_graph(model)
        self.today = (today or date.today()).isoformat()

    def say(self, text: str, thread: str = "demo", customer: str = "guest") -> Turn:
        """A customer sends a message."""
        config = self._config(thread, customer)
        if self.graph.get_state(config).next:
            # The thread is paused at ask_team. Starting a new run now would
            # throw away the question the team has not answered yet.
            return Turn(reply=HOLDING)
        result = self.graph.invoke({"messages": [HumanMessage(text)]}, config)
        return self._turn(result)

    def team_answers(self, text: str, thread: str = "demo", customer: str = "guest") -> Turn:
        """Someone on the team answers a handoff, and the thread carries on."""
        result = self.graph.invoke(Command(resume=text), self._config(thread, customer))
        return self._turn(result)

    def state(self, thread: str = "demo") -> dict:
        return self.graph.get_state(self._config(thread, "guest")).values

    def _config(self, thread: str, customer: str) -> dict:
        return {"configurable": {"thread_id": thread, "customer": customer, "today": self.today}}

    @staticmethod
    def _turn(result: dict) -> Turn:
        waiting = result.get("__interrupt__")
        if waiting:
            return Turn(handoff=waiting[0].value)
        return Turn(reply=result["messages"][-1].content)
