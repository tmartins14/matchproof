import asyncio
from typing import Any

from helpers import call, client_for, fill, finished, validator
from intel.registry import FactRegistry
from mcp_match import MAX_MATCHES, InMemoryMatchStore
from mcp_match.server import MAX_EVENTS, MAX_FACTS
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief

READ_TOOLS = {
    "get_brief",
    "get_fact",
    "find_facts",
    "get_events",
    "get_freeze_frame",
    "list_beats",
    "get_beat_bundle",
}


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def red_card_follow_up(beats: list[dict[str, Any]]) -> dict[str, Any]:
    card = next(b for b in beats if b["kind"] == "card")
    return next(
        b
        for b in beats
        if b["kind"] == "momentum_swing"
        and b["anchor_event_id"] == card["anchor_event_id"]
    )


def test_read_only_server_has_no_write_tool_and_internal_one_has() -> None:
    store, _ = finished()

    async def names(writable: bool) -> set[str]:
        async with client_for(store, writable) as s:
            return {t.name for t in (await s.list_tools()).tools}

    assert run(names(False)) == READ_TOOLS
    assert run(names(True)) == READ_TOOLS | {"put_claims"}


def test_every_tool_validates_against_its_schema() -> None:
    store, match_id = finished()

    async def scenario() -> None:
        async with client_for(store, False) as s:
            validator("match_brief").validate(
                await call(s, "get_brief", match_id=match_id)
            )

            beats = (await call(s, "list_beats", match_id=match_id))["beats"]
            assert beats
            for b in beats:
                validator("beat").validate(b)

            found = await call(s, "find_facts", match_id=match_id, limit=20)
            assert found["facts"] and found["total"] >= len(found["facts"])
            for f in found["facts"]:
                validator("fact").validate(f)
            one = await call(
                s, "get_fact", match_id=match_id, fact_id=found["facts"][0]["id"]
            )
            assert one == found["facts"][0]
            assert one["display"] and one["source_ids"]

            events = await call(s, "get_events", match_id=match_id, t_from=0, t_to=600)
            assert events["events"]
            for e in events["events"]:
                validator("event").validate(e)
                assert 0 <= e["t"] <= 600

            shots = await call(
                s,
                "get_events",
                match_id=match_id,
                t_from=0,
                t_to=10_000,
                types=["shot"],
            )
            assert shots["events"] and {e["type"] for e in shots["events"]} == {"shot"}

            frame = await call(
                s,
                "get_freeze_frame",
                match_id=match_id,
                event_id=shots["events"][0]["id"],
            )
            validator("position_frame").validate(frame)
            assert frame["freeze_frame_of"] == shots["events"][0]["id"]
            coords = [v for p in frame["players"] for v in p["at"]] + frame["ball"]
            assert all(round(v, 1) == v for v in coords)
            assert all(set(p) == {"id", "side", "at"} for p in frame["players"])

            later = await call(
                s, "list_beats", match_id=match_id, after_t=beats[0]["t_detect"]
            )
            assert [b["id"] for b in later["beats"]] == [
                b["id"] for b in beats if b["t_detect"] > beats[0]["t_detect"]
            ]

    run(scenario())


def test_red_card_follow_up_bundle_has_every_cited_fact() -> None:
    store, match_id = finished()

    async def scenario() -> None:
        async with client_for(store, False) as s:
            beats = (await call(s, "list_beats", match_id=match_id))["beats"]
            card = next(b for b in beats if b["kind"] == "card")
            beat = red_card_follow_up(beats)
            bundle = await call(
                s, "get_beat_bundle", match_id=match_id, beat_id=beat["id"]
            )
            assert bundle["beat"] == beat
            assert [f["id"] for f in bundle["facts"]] == beat["fact_ids"]
            for f in bundle["facts"]:
                validator("fact").validate(f)
            ten_men = card["side"]
            assert any(
                f["name"].startswith("back_line_change(")
                and f["scope"]["side"] == ten_men
                for f in bundle["facts"]
            )

    run(scenario())


def test_put_claims() -> None:
    store = InMemoryMatchStore()
    match_id = fill(store, "red_card_flip", 3)

    def claim(cid: str, beat_id: str, fact_ids: list[str]) -> dict[str, Any]:
        return {
            "id": cid,
            "beat_id": beat_id,
            "lang": "en",
            "text": "Ten men drop deeper.",
            "fact_ids": fact_ids,
            "numbers": [],
            "verdict": "checking",
        }

    async def scenario() -> None:
        async with client_for(store, True) as s:
            beats = (await call(s, "list_beats", match_id=match_id))["beats"]
            beat = red_card_follow_up(beats)
            fact_id = beat["fact_ids"][0]

            ok = await call(
                s,
                "put_claims",
                match_id=match_id,
                beat_id=beat["id"],
                claims=[claim("cl-001-01", beat["id"], [fact_id])],
            )
            assert ok["results"] == [
                {"index": 0, "claim_id": "cl-001-01", "accepted": True, "errors": []}
            ]
            validator("claim").validate(
                store.claims(match_id)[beat["id"]][0].model_dump(
                    mode="json", by_alias=True, exclude_none=True
                )
            )

            mixed = await call(
                s,
                "put_claims",
                match_id=match_id,
                beat_id=beat["id"],
                claims=[
                    claim("cl-002-01", beat["id"], ["fx-no-such-fact"]),
                    claim("cl-003-01", beat["id"], [fact_id]),
                    claim("cl-001-01", beat["id"], [fact_id]),
                    {"id": "not-a-claim"},
                ],
            )
            accepted = [r["accepted"] for r in mixed["results"]]
            assert accepted == [False, True, False, False]
            assert "Unknown fact id fx-no-such-fact." in mixed["results"][0]["errors"]
            assert "already used" in mixed["results"][2]["errors"][0]
            assert [c.id.root for c in store.claims(match_id)[beat["id"]]] == [
                "cl-001-01",
                "cl-003-01",
            ]

            number = claim("cl-004-01", beat["id"], [fact_id])
            number["numbers"] = [{"as_written": "7", "fact_id": "fx-nope"}]
            wrong_beat = claim("cl-005-01", "bt-999999-card", [fact_id])
            blocked = claim("cl-006-01", beat["id"], [fact_id])
            blocked["verdict"] = "blocked"
            out = await call(
                s,
                "put_claims",
                match_id=match_id,
                beat_id=beat["id"],
                claims=[number, wrong_beat, blocked],
            )
            assert [r["accepted"] for r in out["results"]] == [False, False, False]
            assert "Unknown fact id fx-nope." in out["results"][0]["errors"]
            assert "not " + beat["id"] in out["results"][1]["errors"][0]
            assert "needs reason and draft_text" in out["results"][2]["errors"][0]

            unknown = await s.call_tool(
                "put_claims",
                {
                    "match_id": match_id,
                    "beat_id": "bt-999999-card",
                    "claims": [claim("cl-007-01", "bt-999999-card", [fact_id])],
                },
            )
            assert unknown.isError
            assert "Unknown beat bt-999999-card" in str(unknown.content)
            assert len(store.claims(match_id)[beat["id"]]) == 2

    run(scenario())


def test_limits_are_capped() -> None:
    store, match_id = finished()

    async def scenario() -> None:
        async with client_for(store, False) as s:
            facts = await call(s, "find_facts", match_id=match_id, limit=100_000)
            assert len(facts["facts"]) == MAX_FACTS
            assert facts["total"] > MAX_FACTS
            events = await call(
                s, "get_events", match_id=match_id, t_from=0, t_to=10_000, limit=100_000
            )
            assert len(events["events"]) == MAX_EVENTS
            assert events["total"] > MAX_EVENTS
            few = await call(
                s, "find_facts", match_id=match_id, name_prefix="field", limit=3
            )
            assert len(few["facts"]) <= 3
            assert all(f["name"].startswith("field") for f in few["facts"])
            home = await call(
                s, "find_facts", match_id=match_id, side="home", limit=200
            )
            assert home["facts"] and all(
                f["scope"]["side"] == "home" for f in home["facts"]
            )
            window = await call(
                s, "find_facts", match_id=match_id, t_from=100, t_to=200, limit=200
            )
            assert all(
                f["scope"]["t_to"] >= 100 and f["scope"]["t_from"] <= 200
                for f in window["facts"]
            )

    run(scenario())


def test_unknown_ids_are_tool_errors_not_traces() -> None:
    store, match_id = finished()
    bad = [
        ("get_brief", {"match_id": "nope"}, "Unknown match nope."),
        (
            "get_fact",
            {"match_id": match_id, "fact_id": "fx-nope"},
            "Unknown fact fx-nope",
        ),
        ("get_fact", {"match_id": "nope", "fact_id": "fx-x"}, "Unknown match nope."),
        ("find_facts", {"match_id": "nope"}, "Unknown match nope."),
        (
            "find_facts",
            {"match_id": match_id, "side": "left"},
            "side must be home or away.",
        ),
        ("find_facts", {"match_id": match_id, "limit": 0}, "limit must be at least 1."),
        (
            "get_events",
            {"match_id": "nope", "t_from": 0, "t_to": 1},
            "Unknown match nope.",
        ),
        (
            "get_freeze_frame",
            {"match_id": match_id, "event_id": "ev-999999"},
            "No freeze frame for event ev-999999",
        ),
        ("list_beats", {"match_id": "nope"}, "Unknown match nope."),
        (
            "get_beat_bundle",
            {"match_id": match_id, "beat_id": "bt-nope"},
            "Unknown beat bt-nope",
        ),
    ]

    async def scenario() -> None:
        async with client_for(store, False) as s:
            for tool, args, message in bad:
                result = await s.call_tool(tool, args)
                text = str(result.content)
                assert result.isError, tool
                assert message in text, (tool, text)
                assert "Traceback" not in text

    run(scenario())


def test_seventh_match_evicts_the_least_recently_used() -> None:
    store = InMemoryMatchStore()
    briefs = [
        make_brief(DEFAULT_HOME, DEFAULT_AWAY, "red_card_flip", seed)
        for seed in range(MAX_MATCHES + 1)
    ]
    ids = [b.match_id for b in briefs]
    for b in briefs[:MAX_MATCHES]:
        store.begin(b, FactRegistry())
    store.brief(ids[0])  # the first is used again, so the second is now the oldest
    store.begin(briefs[MAX_MATCHES], FactRegistry())
    assert ids[1] not in store
    assert all(i in store for i in [ids[0], *ids[2:]])


def test_public_server_hides_beats_past_the_playback_position() -> None:
    store = InMemoryMatchStore()
    match_id = fill(store, "red_card_flip", 3)
    full = finished()[0]
    assert match_id == finished()[1]
    first, last = full.beats(match_id)[0], full.beats(match_id)[-1]
    assert first.t_detect.root < last.t_detect.root
    store._records[match_id].finished = False  # as if still streaming
    store.set_playback(match_id, first.t_detect.root)

    async def scenario() -> None:
        async with (
            client_for(store, False) as public,
            client_for(store, True) as internal,
        ):
            seen = (await call(public, "list_beats", match_id=match_id))["beats"]
            full_list = (await call(internal, "list_beats", match_id=match_id))["beats"]
            assert len(full_list) == len(store.beats(match_id)) > len(seen) >= 1
            assert all(b["t_detect"] <= first.t_detect.root for b in seen)
            hidden = await public.call_tool(
                "get_beat_bundle", {"match_id": match_id, "beat_id": last.id.root}
            )
            assert hidden.isError
            events = await call(
                public, "get_events", match_id=match_id, t_from=0, t_to=6000
            )
            assert all(e["t"] <= first.t_detect.root for e in events["events"])
            for f in (await call(public, "find_facts", match_id=match_id))["facts"]:
                assert f["scope"]["t_to"] <= first.t_detect.root or f["id"] in {
                    x.root for x in first.fact_ids
                }
        store.finish(match_id)
        async with client_for(store, False) as public:
            done = (await call(public, "list_beats", match_id=match_id))["beats"]
            assert len(done) == len(store.beats(match_id))

    run(scenario())
