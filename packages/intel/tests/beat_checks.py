"""The planted-beat check over every storyline and seed, shared by the tests and the memory test."""

from contracts.models import Beat
from matches import compute_lean
from sim.brief import DEFAULT_AWAY, DEFAULT_HOME, make_brief

STORIES = ("late_comeback", "red_card_flip", "smash_and_grab", "end_to_end")
SEEDS = (1, 2, 3, 4)
# The beat kinds a planted beat may be detected as. A penalty has no restart event of its own, so it
# reads as an open-play goal.
EXPECTED_KINDS = {
    "counter_goal": {"counter_goal"},
    "set_piece_goal": {"set_piece_goal"},
    "high_turnover_goal": {"high_turnover_goal"},
    "open_play_goal": {"open_play_goal"},
    "red_card": {"card"},
    "penalty": {"open_play_goal"},
}


def check_planted(story: str, seed: int, beats: list[Beat]) -> None:
    brief = make_brief(DEFAULT_HOME, DEFAULT_AWAY, story, seed)
    for planted in brief.planted_beats:
        kinds = EXPECTED_KINDS[planted.kind.value]
        found = [
            b
            for b in beats
            if b.planted_beat_id == planted.id and b.kind.value in kinds
        ]
        assert found, (
            f"{story}/{seed}: {planted.id} {planted.kind.value} not detected as {kinds}"
        )
        assert all(b.origin.value == "planted" for b in found)
    for b in beats:
        assert (b.origin.value == "planted") == (b.planted_beat_id is not None)
        if b.kind.value in ("momentum_swing", "territorial_spell"):
            assert b.origin.value == "detected"


def run_planted_matrix() -> dict[tuple[str, int], int]:
    """Build and check all 16 matches one after another; returns the beat count of each."""
    counts: dict[tuple[str, int], int] = {}
    for story in STORIES:
        for seed in SEEDS:
            beats = compute_lean(story, seed).beats
            check_planted(story, seed, beats)
            counts[(story, seed)] = len(beats)
    return counts
