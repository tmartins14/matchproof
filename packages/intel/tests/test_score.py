import re

from intel.labels import LabelContext, label_for
from intel.score import lead_text, match_score, score_text
from matches import lean

TEAMS = {"home": "Rivermouth", "away": "Ashford Vale"}
SCORES = ["1–0", "1–1", "2–1", "2–2", "3–2", "3–3"]


def goals() -> list[str]:
    m = lean("end_to_end", 1)
    return [
        e.id.root
        for e in m.events
        if e.type.value == "shot" and e.outcome and e.outcome.value == "goal"
    ]


def test_the_score_after_each_goal_follows_the_match() -> None:
    m = lean("end_to_end", 1)
    ids = goals()
    scores = [m.registry.by_name(f"score_after({g})") for g in ids]
    assert [re.search(r"\d–\d", str(f.value))[0] for f in scores] == SCORES  # type: ignore[index]
    assert scores[0].value == "Rivermouth 1–0 Ashford Vale"
    assert "1–0" in scores[0].display.en  # the bare score reconciles too


def test_the_lead_follows_the_score() -> None:
    m = lean("end_to_end", 1)
    leads = [str(m.registry.by_name(f"lead({g})").value) for g in goals()]
    assert leads == [
        "Rivermouth lead",
        "level",
        "Rivermouth lead",
        "level",
        "Rivermouth lead",
        "level",
    ]


def test_score_facts_cite_the_goals_so_far() -> None:
    m = lean("end_to_end", 1)
    ids = goals()
    for n, g in enumerate(ids, start=1):
        fact = m.registry.by_name(f"score_after({g})")
        assert [s.root for s in fact.source_ids] == sorted(ids[:n])


def test_match_score_at_any_time() -> None:
    m = lean("end_to_end", 1)
    by_id = {e.id.root: e for e in m.events}
    first, second = (by_id[g].t.root for g in goals()[:2])
    assert match_score(m.events, 0.0) == (0, 0)
    assert match_score(m.events, first) == (1, 0)
    assert match_score(m.events, second - 1) == (1, 0)
    assert match_score(m.events, second) == (1, 1)
    assert match_score(m.events) == (3, 3)


def test_score_and_lead_text() -> None:
    assert score_text(0, 2, TEAMS) == "Rivermouth 0–2 Ashford Vale"
    assert lead_text(0, 2, TEAMS) == "Ashford Vale lead"
    assert lead_text(1, 1, TEAMS) == "level"


def test_score_labels() -> None:
    m = lean("end_to_end", 1)
    ctx = LabelContext(TEAMS, {e.id.root: e for e in m.events}, m.registry)
    g = goals()[0]
    assert label_for(m.registry.by_name(f"score_after({g})"), ctx) == (
        "score after the goal"
    )
    assert label_for(m.registry.by_name(f"lead({g})"), ctx) == "who leads"
