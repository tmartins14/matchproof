"""The one place numbers are rounded and written out. Every rendering uses digits.

render() returns the renderings the reconciler will accept for a fact value. Extractors never format
numbers themselves.
"""

from decimal import ROUND_HALF_UP, Decimal

Value = float | int | str | bool

PCT_DECIMALS = 0  # percentages are shown as whole numbers
METRE_DECIMALS = 0  # metres, and square metres, are shown as whole numbers
SECOND_DECIMALS = 0  # seconds are shown as whole numbers
XG_DECIMALS = 2  # the primary xG rendering
XG_SHORT_DECIMALS = 1  # the shorter xG rendering also accepted
SPEED_DECIMALS = 1  # metres per second
PP_DECIMALS = 0  # percentage points are shown as whole numbers
SECONDS_PER_MINUTE = 60

UNIT_DECIMALS = {
    "pct": PCT_DECIMALS,
    "m": METRE_DECIMALS,
    "m2": METRE_DECIMALS,
    "s": SECOND_DECIMALS,
    "xg": XG_DECIMALS,
    "m_s": SPEED_DECIMALS,
    "pp": PP_DECIMALS,
}


def round_half_up(value: float, decimals: int) -> Decimal:
    """Round the way a reader would (0.5 goes up), not the way Python's round() does."""
    return Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)


def display_value(value: float, unit: str) -> float:
    """The value as it is shown in English, for arithmetic that must agree with the prose."""
    return float(round_half_up(value, UNIT_DECIMALS.get(unit, 0)))


def _number(value: float, decimals: int, lang: str) -> str:
    text = f"{round_half_up(value, decimals):f}"
    return text.replace(".", ",") if lang == "es" else text


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def render(value: Value, unit: str, lang: str) -> list[str]:
    """Renderings of a value in a unit, most natural first. Strings and booleans pass through."""
    if isinstance(value, bool):
        return [str(value).lower()]
    if isinstance(value, str):
        return [value]
    es = lang == "es"
    if unit == "pct":
        pct = float(value) * 100
        n = _number(pct, PCT_DECIMALS, lang)
        return [f"{n} %"] if es else [f"{n}%", f"{n} per cent"]
    if unit == "m":
        n = _number(value, METRE_DECIMALS, lang)
        return [f"{n} m"] if es else [f"{n} m", f"{n} metres"]
    if unit == "m2":
        n = _number(value, METRE_DECIMALS, lang)
        return (
            [f"{n} m²", f"{n} metros cuadrados"]
            if es
            else [f"{n} m²", f"{n} square metres"]
        )
    if unit == "s":
        n = _number(value, SECOND_DECIMALS, lang)
        return [f"{n} segundos", f"{n} s"] if es else [f"{n} seconds", f"{n} s"]
    if unit == "xg":
        return _unique(
            [
                f"{_number(value, XG_DECIMALS, lang)} xG",
                f"{_number(value, XG_SHORT_DECIMALS, lang)} xG",
            ]
        )
    if unit == "m_s":
        return [f"{_number(value, SPEED_DECIMALS, lang)} m/s"]
    if unit == "pp":
        n = _number(value, PP_DECIMALS, lang)
        return [f"{n} pp"] if es else [f"{n} pp", f"{n} percentage points"]
    if isinstance(value, int):
        return [str(value)]
    return [_number(value, XG_DECIMALS, lang).rstrip("0").rstrip(",.")]


def minute_of(t: float) -> int:
    """The football minute a match-clock time falls in: 40:12 is in the 41st minute."""
    return int(t // SECONDS_PER_MINUTE) + 1


STOPPAGE_AFTER_MIN = {
    1: 45,
    2: 90,
}  # minutes after which a half's labels read 45+n and 90+n


def minute_text(t: float, period: int) -> str:
    """41, or 45+2 / 90+3 once the half is past its 45th / 90th minute."""
    m = minute_of(t)
    limit = STOPPAGE_AFTER_MIN.get(period)
    return f"{limit}+{m - limit}" if limit is not None and m > limit else str(m)


def render_minute(t: float, lang: str, period: int | None = None) -> list[str]:
    """The broadcast minute: 41′, 45+2′, 90+8′. Without a period there is no stoppage form."""
    text = minute_text(t, period) if period is not None else str(minute_of(t))
    return [f"{text}′"]


def render_clock(t: float, lang: str) -> list[str]:
    """Match clock as mm:ss, the way a producer reads a clip in and out point."""
    whole = int(t)
    return [f"{whole // SECONDS_PER_MINUTE}:{whole % SECONDS_PER_MINUTE:02d}"]
