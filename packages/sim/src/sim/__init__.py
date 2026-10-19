"""Matchproof sim package: tactics in, a full match of events out."""

from collections.abc import Iterator

from contracts.models import Event, MatchBrief

from .engine import _Engine


def iter_events(brief: MatchBrief) -> Iterator[Event]:
    """The match lazily, in time order. Same events as generate()."""
    return _Engine(brief).run()


def generate(brief: MatchBrief) -> list[Event]:
    return list(iter_events(brief))
