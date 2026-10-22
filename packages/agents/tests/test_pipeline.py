import asyncio

from agents.pipeline import Deps, narrate_and_check
from fakes import FakeChat
from helpers import fill, validator
from mcp_match import InMemoryMatchStore, build_server

GOOD = {"supported": True, "problem": None, "reason": "Matches."}


def test_claims_are_written_with_beat_derived_ids_and_match_the_schema() -> None:
    store = InMemoryMatchStore()
    match_id = fill(store, "red_card_flip", 3)
    server = build_server(store, writable=True)
    beat = next(b for b in store.beats(match_id) if b.kind.value == "card")
    fact = store.registry(match_id).get(beat.fact_ids[0].root)
    shown = fact.display.en[0]
    narrator = FakeChat(
        [{"claims": [{"text": f"Card shown: {shown}.", "fact_ids": [fact.id.root]}]}]
    )
    deps = Deps(server=server, narrator=narrator, judge=FakeChat([GOOD]))

    claims = asyncio.run(narrate_and_check(match_id, beat.id.root, "fan", deps=deps))

    assert [c.verdict.value for c in claims] == ["verified"]
    stem = beat.id.root.removeprefix("bt-")
    assert claims[0].id.root == f"cl-{stem}-01"
    stored = store.claims(match_id)[beat.id.root]
    assert len(stored) == 1
    for c in stored:
        validator("claim").validate(
            c.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
