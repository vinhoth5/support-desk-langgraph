"""Command line: chat with the desk, watch a scripted demo, or run the rule check.

    python -m supportdesk            chat as a customer (you also play the team on handoffs)
    python -m supportdesk --demo     a short scripted conversation
    python -m supportdesk --rules    run every rule and print the score
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from .graph import Desk, Turn
from .models import ChatModel
from .rulecheck import run_rules

DEMO = [
    ("customer", "Hi"),
    ("customer", "Where is my order FH5001?"),
    ("customer", "Any update on my parcel?"),
    ("customer", "Do you have the fiddle leaf fig?"),
    ("customer", "How long will it take to deliver to 560034?"),
    ("customer", "I want a refund for order FH5002"),
    ("team", "We've approved a full refund for FH5002. It will reach you in 3 to 5 working days."),
    ("customer", "How much is the jade plant?"),
]


def main() -> int:
    parser = argparse.ArgumentParser(prog="supportdesk", description=__doc__.splitlines()[0])
    parser.add_argument("--demo", action="store_true", help="play a scripted conversation")
    parser.add_argument("--rules", action="store_true", help="run the rule check")
    parser.add_argument("--customer", default="anika", help="whose orders the desk may show (anika or rahul)")
    args = parser.parse_args()

    if args.rules:
        return _rules()
    if args.demo:
        return _demo()
    return _chat(args.customer)


def _rules() -> int:
    results = run_rules()
    for name, passed in results:
        print(f"  {'pass' if passed else 'FAIL'}  {name}")
    passed = sum(ok for _, ok in results)
    print(f"\n{passed} of {len(results)} rules passed")
    return 0 if passed == len(results) else 1


def _demo() -> int:
    desk = Desk(today=date(2026, 11, 13))
    for who, text in DEMO:
        if who == "customer":
            print(f"\nCustomer: {text}")
            _show(desk.say(text, customer="anika"))
        else:
            print(f"Team:     {text}")
            _show(desk.team_answers(text, customer="anika"))
    return 0


def _chat(customer: str) -> int:
    model = ChatModel.from_env() if os.environ.get("SUPPORTDESK_MODEL") else None
    desk = Desk(model=model)
    print(f"Fernhill Nursery help desk. You are '{customer}'. Type 'quit' to leave.")
    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if text.lower() in ("quit", "exit"):
            return 0
        if not text:
            continue
        turn = desk.say(text, customer=customer)
        while turn.handoff:
            _show(turn)
            turn = desk.team_answers(input("Team: ").strip() or "We'll call you shortly.", customer=customer)
        _show(turn)


def _show(turn: Turn) -> None:
    if turn.handoff:
        print(f"  [handed to the team: {turn.handoff['reason']}]")
        for issue in turn.handoff["issues"]:
            print(f"  [guard: {issue}]")
    else:
        print(f"Desk:     {turn.reply}")


if __name__ == "__main__":
    sys.exit(main())
