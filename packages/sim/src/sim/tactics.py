"""Formation slot anchors for a team attacking toward x = 120 (ADR 0007)."""

from typing import Literal

Role = Literal["gk", "def", "mid", "att"]

# 11 slot anchors per formation; slot 0 is the goalkeeper. Positions v1 reuses these.
FORMATIONS: dict[str, list[tuple[float, float]]] = {
    "4-3-3": [
        (6, 40),
        (26, 12),
        (24, 30),
        (24, 50),
        (26, 68),
        (45, 40),
        (52, 24),
        (52, 56),
        (76, 14),
        (80, 40),
        (76, 66),
    ],
    "4-2-3-1": [
        (6, 40),
        (26, 12),
        (24, 30),
        (24, 50),
        (26, 68),
        (42, 32),
        (42, 48),
        (60, 40),
        (66, 16),
        (66, 64),
        (80, 40),
    ],
    "4-4-2": [
        (6, 40),
        (26, 12),
        (24, 30),
        (24, 50),
        (26, 68),
        (46, 14),
        (44, 32),
        (44, 48),
        (46, 66),
        (70, 34),
        (70, 46),
    ],
    "3-5-2": [
        (6, 40),
        (24, 22),
        (22, 40),
        (24, 58),
        (48, 8),
        (44, 30),
        (40, 40),
        (44, 50),
        (48, 72),
        (72, 34),
        (72, 46),
    ],
    "5-3-2": [
        (6, 40),
        (30, 8),
        (22, 24),
        (20, 40),
        (22, 56),
        (30, 72),
        (44, 26),
        (42, 40),
        (44, 54),
        (68, 34),
        (68, 46),
    ],
}


def slot_anchor(formation: str, slot: int, side: str) -> tuple[float, float]:
    """Anchor in absolute coordinates; away mirrors x to 120 - x."""
    x, y = FORMATIONS[formation][slot]
    return (x, y) if side == "home" else (120.0 - x, y)


def role_of(formation: str, slot: int) -> Role:
    """Role from the formation string: first number is defenders, last is attackers."""
    if slot == 0:
        return "gk"
    parts = [int(p) for p in formation.split("-")]
    defenders, attackers = parts[0], parts[-1]
    if slot <= defenders:
        return "def"
    if slot > 10 - attackers:
        return "att"
    return "mid"
