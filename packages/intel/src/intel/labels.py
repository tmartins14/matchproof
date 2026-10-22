"""Plain-English labels for facts, written by code from a fact's name and scope.

The Narrator and the judge read these instead of machine names such as
`back_line_height(away, since ev-001484 to t4671.00)`. Every phrase is a named template below; no
model writes a label. Anchor events are named by what they were (the red card, Rivermouth's goal)
with their broadcast minute, never by id. Labels carry no span lengths, so a claim that copies one
cannot pick up a number that no fact supports.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from contracts.models import Event, Fact

from .display import minute_text
from .registry import FactRegistry

TEAM_FACT = re.compile(r"^(?P<metric>[a-z_]+)\((?P<side>home|away), (?P<rest>.*)\)$")
EVENT_FACT = re.compile(r"^(?P<family>[a-z_]+)\((?P<ev>ev-\d{6})\)\.(?P<key>[a-z_]+)$")
EVENT_ID = re.compile(r"ev-\d{6}")
SINCE = re.compile(r"^since (?P<ev>ev-\d{6}) to t[\d.]+$")
BEFORE = re.compile(r"^before (?P<ev>ev-\d{6})$")
CHANGE = re.compile(r"^(?P<ev>ev-\d{6}), to t[\d.]+$")
PLAYER_ID = re.compile(r"^(?P<side>home|away)-(?P<number>\d{2})$")

# What each team measure is called. {team} is the club name.
TEAM_METRICS: Mapping[str, str] = {
    "back_line_height": "{team} back line",
    "compactness": "{team} shape (area covered, smaller is tighter)",
    "possession_share": "{team} share of possession",
    "territory": "{team} share of play in the opposition half",
    "shots": "{team} shots",
    "xg": "{team} chance quality (xG)",
    "goals": "{team} goals",
    "cards": "{team} cards",
    "corners": "{team} corners",
    "fouls": "{team} fouls",
    "passes": "{team} passes",
    "pass_completion": "{team} pass completion",
    "field_tilt": "{team} share of play near the opposition goal",
    "high_turnovers": "{team} high turnovers (ball won high up the pitch)",
    "press_rate": "{team} pressing rate",
    "pressures_in_opp_third": "{team} pressures in the opposition third",
    "touches_in_opponent_half": "{team} touches in the opposition half",
    "line_breaking_passes": "{team} passes through the lines",
    "line_gap": "{team} gap between the lines",
    "team_length": "{team} team length",
    "team_width": "{team} team width",
}
PHASES: Mapping[str, str] = {
    "in_possession": " with the ball",
    "out_of_possession": " without the ball",
}
# Fixed spans. A span anchored on an event is built from the event (see anchor_phrase).
SPANS: Mapping[str, str] = {
    "match": "over the match",
    "p1": "in the first half",
    "p2": "in the second half",
}
LAST_SPAN = "in the latest spell of play"
WINDOW_SPAN = "in one stretch of the {half} half"
BEFORE_SPAN = "before {anchor}"
SINCE_SPAN = "since {anchor}"

# What each single-event measure is called.
EVENT_METRICS: Mapping[str, str] = {
    "shot.xg": "chance quality (xG)",
    "shot.outcome": "shot result",
    "shot.on_target": "shot on target",
    "shot.minute": "minute of the shot",
    "shot.shooter": "shooter",
    "sequence.seconds": "time from the start of the move to the shot",
    "sequence.passes": "passes in the move",
    "sequence.ball_won_distance": "distance from goal where the ball was won",
    "sequence.start_clock": "minute the move began",
    "sequence.shot_clock": "minute of the shot",
    "card.players_after": "players left after the card",
    "card.minute": "minute of the card",
    "freeze_frame.attackers_v_defenders": "attackers against defenders near the ball",
    "freeze_frame.attackers_ahead_of_ball": "attackers ahead of the ball",
    "freeze_frame.zone_attackers": "attackers in the shooting area",
    "freeze_frame.zone_defenders": "defenders in the shooting area",
    "freeze_frame.defenders_between_ball_and_goal": "defenders between the ball and goal",
    "freeze_frame.defenders_drawn": "defenders pulled towards the ball",
    "freeze_frame.shooter_nearest_defender": "distance to the shooter's nearest defender",
    "freeze_frame.players_bypassed": "opponents bypassed by the pass",
    "freeze_frame.home_ahead_of_ball": "{home} players ahead of the ball",
    "freeze_frame.away_ahead_of_ball": "{away} players ahead of the ball",
}
CARD_KINDS: Mapping[str, str] = {
    "yellow": "card: yellow",
    "red": "card: straight red, sent off",
    "second_yellow": "card: second yellow, sent off",
}
CHANGE_WORDS: Mapping[str, tuple[str, str, str]] = {
    # metric: (word when the later value is lower, when higher, when level)
    "back_line_height": ("dropped deeper", "pushed higher", "held its line"),
    "compactness": ("tightened up", "spread out", "kept its shape"),
}
CHANGE_METRICS: Mapping[str, str] = {
    "back_line_change": "back_line_height",
    "compactness_change": "compactness",
}


@dataclass(frozen=True)
class LabelContext:
    """What a label needs besides the fact: club names, the match's events and its registry."""

    teams: Mapping[str, str]  # side -> club name
    events: Mapping[str, Event]
    registry: FactRegistry


def event_phrase(event: Event, ctx: LabelContext) -> str:
    """What an event was, in words: the red card, Rivermouth's goal, Ashford Vale's corner."""
    team = ctx.teams[event.side.value]
    kind = event.type.value
    outcome = event.outcome.value if event.outcome else None
    if kind == "card":
        return "the red card" if outcome == "red" else "the yellow card"
    if kind == "shot":
        return f"{team}'s goal" if outcome == "goal" else f"{team}'s shot"
    return f"{team}'s {kind.replace('_', ' ')}"


def anchor_phrase(event_id: str, ctx: LabelContext) -> str:
    """The anchor as a viewer would name it, with its broadcast minute: the red card (63′)."""
    event = ctx.events.get(event_id)
    if event is None:
        return "an earlier moment"
    return (
        f"{event_phrase(event, ctx)} ({minute_text(event.t.root, event.period.value)}′)"
    )


def _span_phrase(rest: str, scope_period: int | None, ctx: LabelContext) -> str:
    if rest in SPANS:
        return SPANS[rest]
    if m := BEFORE.match(rest):
        return BEFORE_SPAN.format(anchor=anchor_phrase(m["ev"], ctx))
    if m := SINCE.match(rest):
        return SINCE_SPAN.format(anchor=anchor_phrase(m["ev"], ctx))
    if rest.startswith("last "):
        return LAST_SPAN
    if rest.startswith("win-"):
        return WINDOW_SPAN.format(half="first" if scope_period == 1 else "second")
    return "in this spell"


def _change_label(metric: str, side: str, ev: str, ctx: LabelContext, rest: str) -> str:
    base = CHANGE_METRICS[metric]
    team = ctx.teams[side]
    t_part = rest.split(", to ")[1]
    before_name = f"{base}({side}, before {ev})"
    since_name = f"{base}({side}, since {ev} to {t_part})"
    word = CHANGE_WORDS[base][2]
    if ctx.registry.has_name(before_name) and ctx.registry.has_name(since_name):
        before = float(ctx.registry.by_name(before_name).value)
        since = float(ctx.registry.by_name(since_name).value)
        lower, higher, level = CHANGE_WORDS[base]
        word = lower if since < before else higher if since > before else level
    thing = "back line" if base == "back_line_height" else "shape"
    return f"{team} {thing} {word} since {anchor_phrase(ev, ctx)} (size of the change)"


def _event_label(fact: Fact, m: re.Match[str], ctx: LabelContext) -> str:
    key = f"{m['family']}.{m['key']}"
    if key == "card.kind":
        return CARD_KINDS.get(
            str(fact.value), f"card: {str(fact.value).replace('_', ' ')}"
        )
    template = EVENT_METRICS.get(key)
    if template is None:
        return m["key"].replace("_", " ")
    return template.format(home=ctx.teams["home"], away=ctx.teams["away"])


def label_for(fact: Fact, ctx: LabelContext) -> str:
    """The plain-English label of one fact. Never contains an event id or an underscore."""
    if m := EVENT_FACT.match(fact.name):
        return _event_label(fact, m, ctx)
    if m := TEAM_FACT.match(fact.name):
        metric, side, rest = m["metric"], m["side"], m["rest"]
        period = fact.scope.period.value if fact.scope and fact.scope.period else None
        if metric in CHANGE_METRICS and (c := CHANGE.match(rest)):
            return _change_label(metric, side, c["ev"], ctx, rest)
        phase = ""
        for key, text in PHASES.items():
            if rest.endswith(f", {key}"):
                phase, rest = text, rest[: -len(f", {key}")]
        template = TEAM_METRICS.get(metric, "{team} " + metric.replace("_", " "))
        name = template.format(team=ctx.teams[side])
        return f"{name}{phase}, {_span_phrase(rest, period, ctx)}"
    return EVENT_ID.sub("an earlier moment", fact.name).replace("_", " ")


def say(value: object, display: list[str], teams: Mapping[str, str]) -> list[str]:
    """How a value may be said aloud. Numbers keep their display renderings; machine tokens do not
    reach the Narrator: `second_yellow` becomes `second yellow`, and a player known only by id
    becomes `the Ashford Vale No. 10`."""
    if isinstance(value, str) and not isinstance(value, bool):
        if m := PLAYER_ID.match(value):
            return [f"the {teams[m['side']]} No. {int(m['number'])}"]
        return [value.replace("_", " ")]
    return list(display)


def spoken_values(fact: Fact, ctx: LabelContext) -> list[str]:
    return say(fact.value, fact.display.en, ctx.teams)


def labels_for(facts: Mapping[str, Fact], ctx: LabelContext) -> dict[str, str]:
    return {fid: label_for(f, ctx) for fid, f in facts.items()}
