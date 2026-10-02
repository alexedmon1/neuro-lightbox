"""What a reported result says, in words — the reporting contract.

Every number a digest shows carries its magnitude, its measure, its direction,
its uncertainty where it exists, and the correction behind its significance
(NEURO_LIGHTBOX_PLAN.md §6, Phase 3). What a table does not record is said to be
not recorded, never filled in with a default.

The vocabulary below is the output specification's (§4): ``p_kind`` —
``"fdr"``, ``"fwe"`` (family-wise), ``"corrected"`` (corrected, procedure
named only by ``method``), ``"perm"``, ``"uncorrected"``, ``"ci"`` (significance
read from a confidence interval), or None (not recorded); ``test_kind`` —
``"two_group"``, ``"one_sample"``, ``"regression"``, ``"omnibus"``,
``"equivalence"``, ``"decoding"``, or None. A profile reads them from its tables
(or, for trees written before the specification, from what its package's
columns record); this module turns them into words. Everything returned is
HTML-safe.
"""

from __future__ import annotations

from html import escape

ALPHA = 0.05

MINUS = "−"


def number(value: float, digits: int = 2) -> str:
    """``value`` to ``digits`` decimals, with a typographic minus."""
    text = f"{value:.{digits}f}"
    return text.replace("-", MINUS) if text.startswith("-") else text


def p_text(p: float | None, symbol: str = "p") -> str:
    """``p = .021`` / ``q < .001`` — the statistic's own symbol, no leading zero."""
    if p is None:
        return ""
    if p < 0.001:
        return f"{escape(symbol)} &lt; .001"
    return f"{escape(symbol)} = " + f"{p:.3f}".replace("0.", ".", 1)


def correction_statement(p_kind: str | None, method: str | None = None,
                         symbol: str = "p", alpha: float = ALPHA) -> str:
    """The threshold a result was judged against, and the correction behind it.

    ``method`` names the procedure when the table records it (e.g. ``BH``,
    ``cluster permutation``, ``NBS``). Without a ``p_kind`` the statement says
    the correction was not recorded — it never assumes one.
    """
    a = f"{alpha:g}"
    m = f" ({escape(method)})" if method else ""
    if p_kind == "fdr":
        return f"FDR{m} {escape(symbol)} &lt; {a}"
    if p_kind == "fwe":
        return f"family-wise corrected{m} p &lt; {a}"
    if p_kind == "corrected":
        return (f"corrected{m} p &lt; {a}" if method
                else f"corrected p &lt; {a}, correction method not recorded")
    if p_kind == "perm":
        return f"permutation p &lt; {a}, multiple-comparison correction not recorded"
    if p_kind == "uncorrected":
        return f"uncorrected p &lt; {a}"
    if p_kind == "ci":
        return "95% CI excluding 0, multiple-comparison correction not recorded"
    return f"{escape(symbol)} &lt; {a}, correction not recorded"


def effect_text(value: float, measure: str | None, ci: tuple | None = None,
                signed_magnitude: bool = False) -> str:
    """``g = 0.45 [0.10, 0.80]``. ``measure`` is display HTML (e.g. ``g``,
    ``&omega;&sup2;<sub>p</sub>``); without one the value reads as an effect of
    unrecorded measure. ``signed_magnitude`` shows |value| (a direction arrow
    beside it carries the sign); the CI is then reflected to match."""
    v = abs(value) if signed_magnitude else value
    out = f"{measure or 'effect'} = {number(v)}"
    if ci is not None and ci[0] is not None and ci[1] is not None:
        lo, hi = ci
        if signed_magnitude and value < 0:
            lo, hi = -hi, -lo
        out += f" [{number(lo)}, {number(hi)}]"
    return out


def direction_text(test_kind: str | None, group_a: str | None = None,
                   group_b: str | None = None) -> str:
    """What ▲ means for one test: which group is higher, an increase, a
    positive association — or, when the test is not recorded, only the sign."""
    if test_kind == "two_group" and group_a and group_b:
        return f"&#9650; = {escape(group_a)} &gt; {escape(group_b)}"
    if test_kind == "one_sample":
        return "&#9650; = increase"
    if test_kind == "regression":
        return "&#9650; = positive association"
    if test_kind == "omnibus":
        return "omnibus test, no direction"
    if test_kind == "equivalence":
        if group_a and group_b:
            return f"equivalence test (TOST), {escape(group_a)} vs {escape(group_b)}"
        return "equivalence test (TOST)"
    if test_kind == "decoding":
        return "decoding against chance"
    return "&#9650; = positive (the test's direction is not recorded)"


def arrow(value: float | None) -> str:
    """▲ for a positive value, ▼ for a negative one."""
    return ('<span class="arrow up">&#9650;</span>' if (value or 0) > 0
            else '<span class="arrow down">&#9660;</span>')
