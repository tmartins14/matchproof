from agents.reconcile import reconcile
from fakes import bundle_of, fact

DROP = fact("fx-drop", "7 m", "7 metres")
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
