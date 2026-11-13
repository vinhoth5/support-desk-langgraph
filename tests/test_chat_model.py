"""The LLM path, tested with a fake chat model so no API key is needed."""

from datetime import date

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from supportdesk import ChatModel, Desk


def chat(*responses: str) -> ChatModel:
    return ChatModel(FakeListChatModel(responses=list(responses)))


def test_understand_reads_json_even_when_the_model_wraps_it_in_prose():
    model = chat('Sure! ```json\n{"intent": "order_status", "order_id": "fh5001", "pincode": null, "product_query": null}\n```')
    seen = model.understand("where's my order fh5001", None)
    assert (seen.intent, seen.order_id) == ("order_status", "FH5001")


def test_understand_falls_back_to_rules_when_the_model_ignores_the_format():
    seen = chat("I think they want to know about an order.").understand("Where is my order FH5001?", None)
    assert (seen.intent, seen.order_id) == ("order_status", "FH5001")


def test_understand_rejects_an_intent_that_does_not_exist():
    seen = chat('{"intent": "sell_them_a_car"}').understand("How much is the snake plant?", None)
    assert seen.intent == "product"


def test_a_good_llm_reply_goes_straight_out():
    desk = Desk(
        model=chat(
            '{"intent": "product", "order_id": null, "pincode": null, "product_query": "snake plant"}',
            "The Snake Plant is ₹349 and we have it in stock.",
        ),
        today=date(2026, 11, 13),
    )
    assert desk.say("How much is the snake plant?").reply == "The Snake Plant is ₹349 and we have it in stock."
    assert desk.state()["drafts_written"] == 1


def test_an_llm_that_invents_a_price_is_sent_back_to_rewrite():
    desk = Desk(
        model=chat(
            '{"intent": "product", "order_id": null, "pincode": null, "product_query": "snake plant"}',
            "The Snake Plant is ₹199, a real bargain!",
            "The Snake Plant is ₹349 and in stock.",
        ),
        today=date(2026, 11, 13),
    )
    assert desk.say("How much is the snake plant?").reply == "The Snake Plant is ₹349 and in stock."
    assert desk.state()["drafts_written"] == 2


def test_an_llm_that_keeps_inventing_is_handed_to_the_team():
    desk = Desk(
        model=chat(
            '{"intent": "product", "order_id": null, "pincode": null, "product_query": "snake plant"}',
            "The Snake Plant is ₹199.",
            "Sorry, the Snake Plant is ₹189.",
        ),
        today=date(2026, 11, 13),
    )
    turn = desk.say("How much is the snake plant?")
    assert turn.reply is None
    assert turn.handoff["reason"] == "The agent could not write a reply that matched the facts."
