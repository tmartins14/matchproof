"""Fictional rosters. Names come from a fixed in-repo list; never real players."""

import random

from contracts.models import Player1

SURNAMES: list[str] = [
    "Haldane",
    "Quain",
    "Okafor-Lind",
    "Brennick",
    "Vasko",
    "Tolliver",
    "Marchetti-Roe",
    "Dunmore",
    "Aldous",
    "Pryce",
    "Kowal",
    "Ferreday",
    "Ostrander",
    "Beaumont-Hale",
    "Sandoval-Ray",
    "Throgmorton",
    "Ilesanmi",
    "Carrow",
    "Wexley",
    "Lindqvist-Ames",
    "Dacosta-Penn",
    "Rudolph",
    "Nakamura-Webb",
    "Fenwick-Ode",
    "Harkness",
    "Ibarra-Cole",
    "Jessop",
    "Kellaway",
    "Lombardi-Fry",
    "Mbeki-Strand",
    "Nordahl",
    "Oyelaran",
    "Penhallow",
    "Quigley-Moss",
    "Rasmussen-Teague",
    "Sorrell",
    "Tavares-Gill",
    "Underhill",
    "Voss-Merrick",
    "Whitcombe",
    "Yarrow",
    "Zelenko",
    "Abernathy",
    "Bellamy-Cruz",
    "Castellan",
    "Drummond-Shaw",
]

# Shirt number by slot (slot 0 is the goalkeeper).
SHIRT_NUMBERS: list[int] = [1, 2, 5, 4, 3, 6, 8, 7, 11, 9, 10]
# Pace range for outfield players, m/s.
OUTFIELD_PACE: tuple[float, float] = (7.4, 9.6)
# Pace range for the goalkeeper, m/s; below every outfield player.
KEEPER_PACE: tuple[float, float] = (7.0, 7.3)


def make_roster(side: str, seed: int) -> list[Player1]:
    """11 players, ids home-01 / away-01 upward, slot = id number - 1. Deterministic per seed and side."""
    rng = random.Random(seed)
    names = SURNAMES[:]
    rng.shuffle(names)
    chosen = names[:11] if side == "home" else names[11:22]
    paces = random.Random(f"{seed}-{side}-pace")
    players: list[Player1] = []
    for slot in range(11):
        lo, hi = KEEPER_PACE if slot == 0 else OUTFIELD_PACE
        players.append(
            Player1.model_validate(
                {
                    "id": f"{side}-{slot + 1:02d}",
                    "name": chosen[slot],
                    "number": SHIRT_NUMBERS[slot],
                    "slot": slot,
                    "pace": round(paces.uniform(lo, hi), 2),
                }
            )
        )
    return players
