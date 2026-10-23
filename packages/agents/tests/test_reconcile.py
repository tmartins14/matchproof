from agents.reconcile import reconcile
from fakes import bundle_of, fact

DROP = fact(
    "fx-drop", "7 m", "7 metres", name="back_line_change(home, ev-000001, to t10.00)"
)
POSS = fact("fx-poss", "64%", "64 per cent")
BUNDLE = bundle_of(DROP, POSS)


def test_number_matching_a_rendering_passes() -> None:
    r = reconcile("Ashford's back line dropped 7 m.", ["fx-drop"], BUNDLE)
    assert r.ok and [(n.as_written, n.fact_id) for n in r.numbers] == [
        ("7 m", "fx-drop")
    ]


def test_wrong_number_fails_and_names_it() -> None:
    r = reconcile("Ashford's back line dropped 8 m.", ["fx-drop"], BUNDLE)
    assert not r.ok and '"8 m"' in r.reasons[0]


def test_per_cent_matches_a_percent_rendering() -> None:
    assert reconcile("Rivermouth have 64 per cent of the ball.", ["fx-poss"], BUNDLE).ok
    assert reconcile("Rivermouth have 64% of the ball.", ["fx-poss"], BUNDLE).ok


def test_same_number_with_a_different_unit_fails() -> None:
    r = reconcile("Ashford's back line dropped 7 seconds.", ["fx-drop"], BUNDLE)
    assert not r.ok


def test_number_with_no_cited_facts_fails() -> None:
    r = reconcile("Rivermouth have 64% of the ball.", [], BUNDLE)
    assert not r.ok and any('"64%"' in x for x in r.reasons)


def test_number_in_an_uncited_fact_fails() -> None:
    assert not reconcile("Rivermouth have 64% of the ball.", ["fx-drop"], BUNDLE).ok


def test_unknown_fact_id_fails() -> None:
    r = reconcile("Ashford go ahead.", ["fx-nope"], BUNDLE)
    assert not r.ok and "fx-nope" in r.reasons[0]


def test_each_number_is_checked() -> None:
    r = reconcile(
        "They dropped 7 m and have 70% of the ball.", ["fx-drop", "fx-poss"], BUNDLE
    )
    assert not r.ok and len(r.reasons) == 1 and '"70%"' in r.reasons[0]


def test_a_player_name_must_come_from_a_cited_fact() -> None:
    scorer = fact("fx-who", "Pryce")
    scorer = scorer.model_copy(update={"value": "Pryce"})
    bundle = bundle_of(scorer, DROP)
    names = {"Pryce", "Dunmore"}
    assert reconcile("Pryce scores.", ["fx-who"], bundle, names).ok
    r = reconcile("Dunmore is sent off.", ["fx-who"], bundle, names)
    assert not r.ok and '"Dunmore"' in r.reasons[0]
    assert not reconcile(
        "Pryce scores.", ["fx-drop"], bundle, names
    ).ok  # fact not cited
    assert reconcile(
        "Pryce-Roe scores.", ["fx-drop"], bundle, names
    ).ok  # another surname


SINCE = fact(
    "fx-since",
    "730 m²",
    "730 square metres",
    name="compactness(away, since ev-001484 to t4671.00)",
)
BEFORE = fact(
    "fx-before",
    "820 m²",
    "820 square metres",
    name="compactness(away, before ev-001484)",
)
CHANGE = fact(
    "fx-change",
    "90 m²",
    "90 square metres",
    name="compactness_change(away, ev-001484, to t4671.00)",
)
SCORE = fact(
    "fx-score",
    "Rivermouth 1–0 Ashford Vale",
    "1–0",
    name="score_after(ev-001670)",
)
LEAD = fact("fx-lead", "Rivermouth lead", name="lead(ev-001670)")
GOAL = fact("fx-goal", "goal", name="shot(ev-001670).outcome")
COMPARING = bundle_of(SINCE, BEFORE, CHANGE, SCORE, LEAD, GOAL)


def test_a_comparative_citing_only_a_since_fact_fails_and_names_the_word() -> None:
    text = "Ashford Vale are defending in a tighter 730 square metres shape."
    r = reconcile(text, ["fx-since"], COMPARING)
    assert not r.ok
    assert r.reasons == ["'tighter' compares, but no before or change fact is cited."]


def test_a_comparative_passes_when_a_before_or_change_fact_is_cited() -> None:
    text = "Ashford Vale are defending in a tighter 730 square metres shape."
    assert reconcile(text, ["fx-since", "fx-change"], COMPARING).ok
    assert reconcile(text, ["fx-since", "fx-before"], COMPARING).ok


def test_edge_in_front_needs_the_lead_or_the_score() -> None:
    text = "Rivermouth edge in front."
    r = reconcile(text, ["fx-goal"], COMPARING)
    assert not r.ok and "'edge in front' compares" in r.reasons[0]
    assert reconcile(text, ["fx-goal", "fx-lead"], COMPARING).ok
    assert reconcile(text, ["fx-goal", "fx-score"], COMPARING).ok


def test_the_score_reconciles_as_a_number() -> None:
    assert reconcile("Rivermouth lead 1–0.", ["fx-score"], COMPARING).ok


def test_text_without_a_comparison_needs_no_comparison_fact() -> None:
    assert reconcile("Pryce scores.", ["fx-goal"], COMPARING).ok


def test_comparison_words_match_whole_words_only() -> None:
    assert reconcile("Ashford Vale are the moreish side.", ["fx-goal"], COMPARING).ok
    assert not reconcile("Ashford Vale have more.", ["fx-goal"], COMPARING).ok
