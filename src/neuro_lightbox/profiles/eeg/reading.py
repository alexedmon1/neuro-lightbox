"""What source-analytics' tables record about each result, in the contract's terms.

Trees written before the output specification carry no ``p_kind`` /
``effect_measure`` / ``test_kind`` fields, but source-analytics' native
hypothesis schema records the same facts in its own columns:

- ``effect_size_type`` — the effect measure (``hedges_g``, ``omega2_partial``,
  ``std_beta``, …); a legacy table's ``hedges_g`` column is Hedges' g by name;
- ``q_value`` with ``fdr_family`` (``method=BH scope=band …``) — FDR-adjusted p
  and the procedure; ``significant`` is ``q_value < 0.05`` (source-analytics
  ``R/hypothesis.R``); ``p_fdr`` / ``q_fdr`` in older tables;
- ``kind`` — ``contrast``, ``omnibus`` or ``equivalence``; an equivalence row's
  ``p_value`` / ``q_value`` / ``significant`` are those of the *difference*
  test, and its TOST outcome is ``equivalent``;
- ``group_a`` / ``group_b`` — the two groups of a contrast.

This module reads only what those columns say. A table without them — another
package's, or an older export — reads as not recorded.
"""

from __future__ import annotations

from html import escape

_DEGENERATE = {"", "na", "nan", "none"}

#: effect_size_type -> display label (HTML).
MEASURES = {
    "hedges_g": "g",
    "cohens_d": "d",
    "cohen_d": "d",
    "omega2_partial": "&omega;&sup2;<sub>p</sub>",
    "eta2_partial": "&eta;&sup2;<sub>p</sub>",
    "std_beta": "&beta;<sub>std</sub>",
    "r": "r",
}
#: effect_size_type -> plain-text name (figure labels).
MEASURE_TEXT = {
    "hedges_g": "Hedges g",
    "cohens_d": "Cohen d",
    "cohen_d": "Cohen d",
    "omega2_partial": "partial \u03c9\u00b2",
    "eta2_partial": "partial \u03b7\u00b2",
    "std_beta": "standardized \u03b2",
    "r": "r",
}
#: Measures with no sign: no direction arrow, and not compared with signed ones.
UNSIGNED = {"omega2_partial", "eta2_partial"}

#: The legacy effect columns, by name.
COLUMN_MEASURES = {"hedges_g": "g", "coefficient": "&beta;", "auc": "AUC",
                   "accuracy": "accuracy"}


def _present(value) -> bool:
    return value is not None and str(value).strip().lower() not in _DEGENERATE


def measure(rec: dict, headers, effect_col: str) -> str | None:
    """The effect measure of one row (display HTML), or None when not recorded."""
    if effect_col == "effect_size":
        if "effect_size_type" in headers and _present(rec.get("effect_size_type")):
            t = str(rec["effect_size_type"]).strip()
            return MEASURES.get(t, escape(t))
        if "hedges_g" in headers:          # a legacy table read through the alias
            return "g"
        return None
    return COLUMN_MEASURES.get(effect_col)


def signed(rec: dict, headers, effect_col: str) -> bool:
    """Whether the row's effect has a sign (and so a direction)."""
    if effect_col in ("auc", "accuracy"):
        return False
    if effect_col == "effect_size" and "effect_size_type" in headers:
        return str(rec.get("effect_size_type") or "").strip() not in UNSIGNED
    return True


def correction(headers, records) -> dict:
    """How the table's significance was judged: ``{column, symbol, p_kind, method}``.

    The column is the one significance is read from (the first present of the
    corrected columns, else the raw p); ``p_kind`` is None when the table does
    not record a correction.
    """
    def method():
        for r in records:
            fam = str(r.get("fdr_family") or "")
            for token in fam.split():
                if token.startswith("method="):
                    return token.split("=", 1)[1]
        return None

    if "q_value" in headers:
        return {"column": "q_value", "symbol": "q", "p_kind": "fdr", "method": method()}
    for col in ("q_fdr", "p_fdr"):
        if col in headers:
            return {"column": col, "symbol": "q", "p_kind": "fdr", "method": None}
    if "p_corrected" in headers:
        return {"column": "p_corrected", "symbol": "p", "p_kind": "corrected", "method": None}
    for col in ("p_value", "p"):
        if col in headers:
            # A permutation p (decoding) is recorded as such by its permutation count.
            kind = "perm" if "n_permutations" in headers else None
            return {"column": col, "symbol": "p", "p_kind": kind, "method": None}
    return {"column": None, "symbol": "p", "p_kind": None, "method": None}


def p_of(rec: dict, corr: dict) -> float | None:
    from .render import _to_float

    return _to_float(rec.get(corr["column"])) if corr["column"] else None


def test_kind(rows: list[dict], headers, effect_col: str, design: dict | None = None) -> str | None:
    """The test behind a contrast's rows: from ``kind`` and the groups the table
    records, else from the study's design for that contrast, else None."""
    first = rows[0] if rows else {}
    kind = str(first.get("kind") or "").strip().lower()
    if kind == "omnibus":
        return "omnibus"
    if kind == "equivalence":
        return "equivalence"
    if effect_col in ("auc", "accuracy"):
        return "decoding"
    if str(first.get("effect_size_type") or "").strip() == "std_beta":
        return "regression"
    if groups(rows, design)[0]:
        return "two_group"
    return None


def groups(rows: list[dict], design: dict | None = None) -> tuple[str | None, str | None]:
    """The two groups of a contrast: from its rows' ``group_a`` / ``group_b``,
    else from the study's design (``{group_a, group_b}``)."""
    first = rows[0] if rows else {}
    a, b = first.get("group_a"), first.get("group_b")
    if _present(a) and _present(b):
        return str(a), str(b)
    design = design or {}
    if design.get("group_a") and design.get("group_b"):
        return str(design["group_a"]), str(design["group_b"])
    return None, None


def plain(statement_html: str) -> str:
    """A contract statement as plain text (figure titles)."""
    import html
    import re

    return html.unescape(re.sub(r"<[^>]+>", "", statement_html))


def one_measure(records: list[dict], headers) -> tuple[list[dict], str, str]:
    """The rows of one effect measure, its plain-text name, and a note naming the
    measures left out — a heatmap never puts two measures on one colour scale.

    The most common ``effect_size_type`` is kept (an omnibus table's ω² rows are
    left out of a contrast's g map). Without the column the measure is Hedges g
    only when the table says so by its ``hedges_g`` column; else not recorded.
    """
    if "effect_size_type" in headers:
        types = [str(r.get("effect_size_type") or "").strip() for r in records]
        counts: dict[str, int] = {}
        for t in types:
            if t:
                counts[t] = counts.get(t, 0) + 1
        if counts:
            main = max(counts, key=lambda t: (counts[t], -types.index(t)))
            kept = [r for r, t in zip(records, types) if t in (main, "")]
            left = [MEASURE_TEXT.get(t, t) for t in counts if t != main]
            note = f"; {', '.join(left)} rows not shown" if left else ""
            return kept, MEASURE_TEXT.get(main, main), note
    if "hedges_g" in headers:
        return records, "Hedges g", ""
    return records, "effect size (measure not recorded)", ""


def star_note(headers, records) -> str:
    """What a ★ marks in a heatmap of these rows, as plain text."""
    from ...contract import correction_statement

    corr = correction(headers, records)
    return "\u2605 = " + plain(correction_statement(corr["p_kind"], corr["method"], corr["symbol"]))
