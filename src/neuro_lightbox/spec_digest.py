"""The summary of an analysis written to the results specification.

Built from what the folder states, never from column names: the correction and
what it is over, the effect measure and its definition, and every test that was
run — significant or not — with its effect, interval, direction, extent and
corrected p. Clusters and elements are summarised largest first, with the count
and a pointer to the full table, which the gallery also embeds.
"""

from __future__ import annotations

import math
from html import escape

from .spec import SpecAnalysis, SpecTable, StudyNames, as_bool, as_float

CLUSTERS_SHOWN = 5


def _fmt(x: float | None, digits: int = 2) -> str:
    """Two decimals, or two significant figures below 0.1 (plain notation down to
    1e-6), so a small estimate keeps its precision and a column reads alike."""
    if x is None:
        return "—"
    if abs(x) >= 1e5 or (x != 0 and abs(x) < 1e-6):
        return f"{x:.{digits}g}"
    if x == 0 or abs(x) >= 0.1:
        return f"{x:.{digits}f}"
    decimals = digits - 1 - math.floor(math.log10(abs(x)))
    return f"{x:.{decimals}f}"


def _p(x: float | None) -> str:
    if x is None:
        return "—"
    return "< 0.001" if x < 0.001 else f"{x:.3f}"


def _significant(row: dict, std: dict, alpha: float) -> bool:
    if "significant" in std:
        flag = as_bool(row.get(std["significant"]))
        if flag is not None:
            return flag
    p = as_float(row.get(std.get("p_value", ""), None))
    return p is not None and p < alpha


def _test_key(row: dict, std: dict) -> tuple[str, str]:
    facet = row.get(std["facet"], "") if "facet" in std else ""
    return facet, row.get(std.get("contrast", ""), "")


def _order(values, preferred):
    pref = {v: i for i, v in enumerate(preferred)}
    seen = []
    for v in values:
        if v not in seen:
            seen.append(v)
    return sorted(seen, key=lambda v: (pref.get(v, len(pref)), seen.index(v)))


def _header(spec: SpecAnalysis) -> str:
    r = spec.record
    html = []
    if r.get("retired"):
        ret = r["retired"] if isinstance(r["retired"], dict) else {}
        html.append('<div class="analysis-warn"><b>Retired</b> — ' + escape(str(ret.get("reason", "")))
                    + (f" Superseded by {escape(str(ret['superseded_by']))}." if ret.get("superseded_by")
                       else "") + "</div>")
    caveats = [str(c) for c in r.get("caveats") or []]
    if caveats:
        html.append('<div class="analysis-warn"><b>Caveats</b><ul>'
                    + "".join(f"<li>{escape(c)}</li>" for c in caveats) + "</ul></div>")
    inf = r.get("inference") or {}
    corr = inf.get("correction") or {}
    eff = r.get("effect") or {}
    design = r.get("design") or {}
    groups = design.get("groups") or {}
    rows = [("Role", r.get("role")),
            ("Design", f"n = {design.get('n')}" + (" (" + ", ".join(
                f"{escape(str(g))} {n}" for g, n in groups.items()) + ")" if groups else "")),
            ("Inference", inf.get("method")),
            ("Correction", corr.get("statement")),
            ("Corrected over", corr.get("family")),
            ("Effect", (f"{eff.get('measure')} — {eff.get('definition', '')}" if eff.get("measure")
                        else f"none: {eff.get('reason', 'not stated')}"))]
    html.append('<dl class="spec-facts">' + "".join(
        f"<dt>{escape(k)}</dt><dd>{escape(str(v)) if k != 'Design' else v}</dd>"
        for k, v in rows if v) + "</dl>")
    dec = r.get("decision")
    if isinstance(dec, dict):
        crit = "".join(
            f"<li>{escape(str(c.get('name', '')))}: "
            f"{'met' if c.get('passed') else 'not met' if c.get('passed') is False else 'not assessed'}"
            f"{' — ' + escape(str(c['description'])) if c.get('description') else ''}</li>"
            for c in dec.get("criteria") or [] if isinstance(c, dict))
        html.append(f'<div class="spec-decision"><b>Decision rule:</b> {escape(str(dec.get("rule", "")))}'
                    f' — <b>{escape(str(dec.get("outcome", "")).replace("_", " "))}</b>'
                    + (f"<ul>{crit}</ul>" if crit else "") + "</div>")
    return "".join(html)


def _tests_html(spec: SpecAnalysis, table: SpecTable, names: StudyNames) -> str:
    std = table.standard()
    _cols, rows = table.read()
    alpha = spec.alpha
    measure_order = spec.measures
    em = table.qualifier("effect_size", "EffectMeasure") or "effect"
    pkind = table.qualifier("p_value", "PKind") or "?"
    pscope = table.qualifier("p_value", "PScope")
    has_extent = "frac_significant" in std or "n_significant" in std
    n_sig = sum(_significant(r, std, alpha) for r in rows)
    html = [f'<p class="spec-lead">{len(rows)} tests ({escape(table.rows_are)}); '
            f'{n_sig} reach {escape(pkind)} p &lt; {alpha:g}. Every test is listed, '
            f'significant or not.</p>']
    keys = _order([_test_key(r, std) for r in rows], [])
    keys = sorted(keys, key=lambda k: names.rank(*k))            # the study's order, if it gives one
    for facet, contrast in keys:
        sel = [r for r in rows if _test_key(r, std) == (facet, contrast)]
        first = sel[0]
        direction = first.get(std["tested_direction"], "") if "tested_direction" in std else ""
        label = first.get(std["contrast_label"], "") if "contrast_label" in std else ""
        title = names.label(facet, contrast)
        raw = " · ".join(x for x in (facet, contrast) if x)
        html.append(f'<h4 class="spec-test">{escape(title)}'
                    + (f' <span class="spec-direction">({escape(raw)})</span>' if title != raw else "")
                    + (f' <span class="spec-direction">tests {escape(direction)}</span>' if direction else "")
                    + "</h4>")
        if label:
            html.append(f'<p class="spec-label">{escape(label)}</p>')
        head = ["Measure", f"{escape(em)} [CI]", "Observed"]
        if has_extent:
            head.append("Extent")
        head += [f"p ({escape(pkind)}{', ' + escape(pscope) if pscope else ''})", "n"]
        body = []
        ms = "measure" in std
        sel = sorted(sel, key=lambda r: (_order([x.get(std["measure"], "") for x in sel], measure_order)
                                          .index(r.get(std["measure"], "")) if ms else 0))
        for r in sel:
            d = as_float(r.get(std.get("effect_size", ""), None))
            lo = as_float(r.get(std.get("effect_ci_low", ""), None))
            hi = as_float(r.get(std.get("effect_ci_high", ""), None))
            eff = _fmt(d) + (f" [{_fmt(lo)}, {_fmt(hi)}]" if lo is not None and hi is not None else "")
            cells = [escape(r.get(std["measure"], "")) if ms else "", eff,
                     escape(r.get(std["observed_direction"], "")) if "observed_direction" in std else ""]
            if has_extent:
                frac = as_float(r.get(std.get("frac_significant", ""), None))
                nsig = as_float(r.get(std.get("n_significant", ""), None))
                ext = (f"{100 * frac:.1f}%" if frac is not None else "")
                ext += (f" ({int(nsig)})" if nsig is not None else "")
                cells.append(ext or "—")
            n = r.get(std["n"], "") if "n" in std else (
                f"{r.get(std.get('n_a', ''), '')} vs {r.get(std.get('n_b', ''), '')}")
            cells += [_p(as_float(r.get(std.get("p_value", ""), None))), escape(str(n))]
            cls = "spec-sig" if _significant(r, std, alpha) else "spec-null"
            body.append(f'<tr class="{cls}">' + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        html.append('<table class="spec-tests"><thead><tr>' + "".join(f"<th>{h}</th>" for h in head)
                    + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>")
    return "".join(html)


def _clusters_html(spec: SpecAnalysis, table: SpecTable) -> str:
    std = table.standard()
    _cols, rows = table.read()
    if not rows:
        return f'<p class="spec-lead">No clusters ({escape(table.rows_are)}).</p>'
    alpha = spec.alpha
    size = std.get("n_voxels") or std.get("volume_mm3")
    groups: dict = {}
    for r in rows:
        key = (r.get(std.get("measure", ""), "") if "measure" in std else "",) + _test_key(r, std)
        groups.setdefault(key, []).append(r)
    html = [f'<h4 class="spec-test">Clusters</h4><p class="spec-lead">{len(rows)} clusters '
            f'({escape(table.rows_are)}) over {len(groups)} tests; per test the '
            f'{CLUSTERS_SHOWN} largest are shown — every cluster is in the table '
            f'{escape(table.path.name)}.</p>']
    space = table.qualifier("peak_xyz_mm", "Space")
    pkind = table.qualifier("p_value", "PKind") or "?"
    for key, sel in groups.items():
        sel = sorted(sel, key=lambda r: -(as_float(r.get(size, None)) or 0))
        title = " · ".join(x for x in key if x)
        html.append(f'<p class="spec-cluster-test"><b>{escape(title)}</b> — {len(sel)} cluster'
                    f'{"s" if len(sel) != 1 else ""}</p><ul class="spec-clusters">')
        for r in sel[:CLUSTERS_SHOWN]:
            bits = []
            if "n_voxels" in std:
                bits.append(f"{r.get(std['n_voxels'])} voxels")
            if "volume_mm3" in std:
                bits.append(f"{_fmt(as_float(r.get(std['volume_mm3'])), 1)} mm³")
            if "peak_region" in std:
                bits.append(f"peak in {escape(r.get(std['peak_region'], '') or 'no atlas region')}")
            if "peak_xyz_mm" in std:
                bits.append(f"at ({escape(r.get(std['peak_xyz_mm'], ''))}){' ' + escape(space) if space else ''}")
            if "stat" in std:
                bits.append(f"peak {escape(table.qualifier('stat', 'StatName') or 'stat')} "
                            f"{_fmt(as_float(r.get(std['stat'])))}")
            if "effect_size" in std:
                sel_flag = as_bool(r.get(std.get("effect_selected", ""), "")) if "effect_selected" in std else None
                bits.append(f"{escape(table.qualifier('effect_size', 'EffectMeasure') or 'effect')} "
                            f"{_fmt(as_float(r.get(std['effect_size'])))}"
                            + (" (selected, inflated)" if sel_flag else ""))
            if "p_value" in std:
                bits.append(f"{escape(pkind)} p {_p(as_float(r.get(std['p_value'])))}")
            if "crosses_midline" in std and as_bool(r.get(std["crosses_midline"])):
                bits.append("crosses the midline")
            cls = "spec-sig" if _significant(r, std, alpha) else "spec-null"
            html.append(f'<li class="{cls}">' + "; ".join(bits) + "</li>")
        html.append("</ul>")
    return "".join(html)


def _elements_html(spec: SpecAnalysis, table: SpecTable) -> str:
    std = table.standard()
    _cols, rows = table.read()
    alpha = spec.alpha
    mag = std.get("effect_size") or std.get("stat")
    sig = [r for r in rows if _significant(r, std, alpha)]
    sig = sorted(sig, key=lambda r: -abs(as_float(r.get(mag, None)) or 0))
    pkind = table.qualifier("p_value", "PKind") or "?"
    html = [f'<h4 class="spec-test">{escape(table.path.stem)}</h4><p class="spec-lead">'
            f'{len(rows)} rows ({escape(table.rows_are)}); {len(sig)} reach {escape(pkind)} '
            f'p &lt; {alpha:g}' + (f'; the {CLUSTERS_SHOWN} largest are listed' if len(sig) > CLUSTERS_SHOWN
                                   else "") + '. Every row is in the table.</p><ul class="spec-clusters">']
    for r in sig[:CLUSTERS_SHOWN]:
        name = " · ".join(r.get(std[t], "") for t in ("measure", "contrast", "element") if t in std)
        html.append(f'<li class="spec-sig">{escape(name)}: {_fmt(as_float(r.get(mag)))}; '
                    f'{escape(pkind)} p {_p(as_float(r.get(std.get("p_value", ""), None)))}</li>')
    return "".join(html) + "</ul>"


def spec_digest(spec: SpecAnalysis, names: StudyNames | None = None) -> str:
    """The summary HTML of one analysis (see module docstring); tests are named and
    ordered by the study config where it says (``names``)."""
    names = names or StudyNames()
    parts = [_header(spec)]
    tests = spec.tables_with_role("tests")
    tests = sorted(tests, key=lambda t: not t.headline)
    for t in tests:
        parts.append(_tests_html(spec, t, names))
    for t in spec.tables_with_role("clusters"):
        parts.append(_clusters_html(spec, t))
    for t in spec.tables_with_role("elements"):
        parts.append(_elements_html(spec, t))
    if not tests:
        parts.append('<p class="spec-lead">This analysis lists no tests table.</p>')
    return '<div class="spec-digest">' + "".join(parts) + "</div>"
