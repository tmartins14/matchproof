import pytest
from intel.display import minute_of, render, render_clock, render_minute
from intel.registry import FactRegistry, build_fact, fact_id
from intel.windows import build_window, windows
from matches import match


def test_english_renderings() -> None:
    assert render(6, "count", "en") == ["6"]
    assert render(0.64, "pct", "en") == ["64%", "64 per cent"]
    assert render(8.0, "m", "en") == ["8 m", "8 metres"]
    assert render(540.0, "m2", "en") == ["540 m²", "540 square metres"]
    assert render(11.0, "s", "en") == ["11 seconds", "11 s"]
    assert render(0.41, "xg", "en") == ["0.41 xG", "0.4 xG"]
    assert render(8.2, "m_s", "en") == ["8.2 m/s"]
    assert render_minute(40.2 * 60, "en") == ["41′"]
    assert render_clock(40 * 60 + 12.7, "en") == ["40:12"]


def test_spanish_renderings() -> None:
    assert render(0.41, "xg", "es") == ["0,41 xG", "0,4 xG"]
    assert render(0.64, "pct", "es") == ["64 %"]
    assert render(8.0, "m", "es") == ["8 m"]
    assert render(11.0, "s", "es") == ["11 segundos", "11 s"]
    assert render(8.2, "m_s", "es") == ["8,2 m/s"]
    assert render(540.0, "m2", "es")[0] == "540 m²"


def test_rounding_goes_up_at_a_half_and_xg_keeps_two_decimals() -> None:
    assert render(0.625, "pct", "en")[0] == "63%"  # 62.5 rounds up, not to even
    assert render(2.5, "m", "en")[0] == "3 m"
    assert render(0.4, "xg", "en") == ["0.40 xG", "0.4 xG"]
    assert render(0.07, "xg", "en")[0] == "0.07 xG"
    assert minute_of(0.0) == 1 and minute_of(59.9) == 1 and minute_of(60.0) == 2


def test_strings_and_booleans_pass_through() -> None:
    assert render("3 v 1", "", "en") == ["3 v 1"]
    assert render(True, "", "en") == ["true"]


def test_fact_ids_are_derived_from_names() -> None:
    assert (
        fact_id("possession_share(home, win-04)") == "fx-possession_share-home-win-04"
    )
    name = "freeze_frame(ev-000597).attackers_ahead_of_ball"
    assert fact_id(name) == "fx-freeze_frame-ev-000597-attackers_ahead_of_ball"
    assert fact_id(name) == fact_id(name)


def test_registry_add_get_and_conflicts() -> None:
    reg = FactRegistry()
    a = build_fact("shots(home, win-01)", 3, "count", ["win-01"], "t")
    assert reg.add(a) is True
    assert reg.add(a) is False
    assert reg.get(a.id.root) == a
    assert reg.by_name("shots(home, win-01)") == a
    with pytest.raises(ValueError, match="conflicting"):
        reg.add(build_fact("shots(home, win-01)", 4, "count", ["win-01"], "t"))
    reg.add(build_fact("shots(away, win-01)", 1, "count", ["win-01"], "t"))
    assert [f.name for f in reg.all()] == ["shots(away, win-01)", "shots(home, win-01)"]


def test_window_table() -> None:
    events = match("red_card_flip", 3).events
    table = windows(events)
    assert [w.id for w in table] == [f"win-0{i}" for i in range(1, 7)]
    assert [w.period for w in table] == [1, 1, 1, 2, 2, 2]
    first, second = table[:3], table[3:]
    assert [(w.t_from, w.t_to) for w in first[:2]] == [(0.0, 900.0), (900.0, 1800.0)]
    assert (
        first[2].t_from == 1800.0 and first[2].t_to > 2700.0
    )  # absorbs the first half's stoppage
    assert second[0].t_from == first[2].t_to  # the clock runs on into the second half
    assert second[1].t_from == second[0].t_from + 900.0
    assert second[2].t_to == events[-1].t.root


def test_last_window_needs_the_end_of_the_half() -> None:
    with pytest.raises(ValueError):
        build_window(3, 0.0, None)
