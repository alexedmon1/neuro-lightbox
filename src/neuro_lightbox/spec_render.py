"""Overview figures of analyses written to the results specification.

One figure per tests table: tests (facet · contrast) by measure, each cell the
test's effect size from the column the dictionary marks ``effect_size``, labelled
with its value, outlined where the test is significant under the analysis's own
correction, and hatched where the interval includes zero. Nulls are drawn like
everything else. A profile adds its own figures (e.g. maps) through
:meth:`~neuro_lightbox.profiles.Profile.render_spec`.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from .scanner import FigureEntry, _slugify
from .spec import SpecAnalysis, SpecTable, as_bool, as_float

#: Effect measures on a standardised scale (the colour scale gets a floor of 0.5).
STANDARDISED = {"d", "g", "cohen's d", "hedges' g", "r", "z", "z_diff"}


def _significant(row, std, alpha):
    if "significant" in std:
        flag = as_bool(row.get(std["significant"]))
        if flag is not None:
            return flag
    p = as_float(row.get(std.get("p_value", ""), None))
    return p is not None and p < alpha


def effect_heatmap(spec: SpecAnalysis, table: SpecTable, out_path: Path, dpi: int = 150) -> Path | None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    std = table.standard()
    if "effect_size" not in std or "contrast" not in std:
        return None
    _cols, rows = table.read()
    if not rows:
        return None
    measures = []
    for m in spec.measures + [r.get(std["measure"], "") for r in rows] if "measure" in std else [""]:
        if m not in measures:
            measures.append(m)
    measures = [m for m in measures if any((r.get(std["measure"], "") if "measure" in std else "") == m
                                           for r in rows)]
    tests = []
    for r in rows:
        key = (r.get(std["facet"], "") if "facet" in std else "", r.get(std["contrast"], ""))
        if key not in tests:
            tests.append(key)
    mat = np.full((len(tests), len(measures)), np.nan)
    sig = np.zeros_like(mat, dtype=bool)
    spans_zero = np.zeros_like(mat, dtype=bool)
    for r in rows:
        i = tests.index((r.get(std["facet"], "") if "facet" in std else "", r.get(std["contrast"], "")))
        j = measures.index(r.get(std["measure"], "") if "measure" in std else "")
        d = as_float(r.get(std["effect_size"]))
        mat[i, j] = np.nan if d is None else d
        sig[i, j] = _significant(r, std, spec.alpha)
        lo = as_float(r.get(std.get("effect_ci_low", ""), None))
        hi = as_float(r.get(std.get("effect_ci_high", ""), None))
        spans_zero[i, j] = lo is not None and hi is not None and lo <= 0 <= hi

    em = table.qualifier("effect_size", "EffectMeasure") or "effect"
    vmax = float(np.nanmax(np.abs(mat))) if np.isfinite(mat).any() else 1.0
    # A standardised effect gets a floor, so a page of small d's is not painted as
    # large; an effect in a measure's own units is scaled to what it is.
    vmax = max(vmax, 0.5) if em.lower() in STANDARDISED else (vmax or 1.0)
    w = 1.6 + 0.8 * len(measures)
    h = 1.4 + 0.36 * len(tests)
    fig, ax = plt.subplots(figsize=(max(w, 4.5), max(h, 2.2)))
    im = ax.imshow(mat, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    for i in range(len(tests)):
        for j in range(len(measures)):
            v = mat[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:+.2g}", ha="center", va="center", fontsize=7,
                        color="white" if abs(v) > 0.6 * vmax else "black",
                        fontweight="bold" if sig[i, j] else "normal")
            if spans_zero[i, j]:                       # independent of significance: a test
                ax.add_patch(plt.Rectangle((j - 0.45, i - 0.45), 0.9, 0.9, fill=False, lw=0,
                                           hatch="////", ec="#999999"))
            if sig[i, j]:                              # can pass while its summary effect's CI spans 0
                ax.add_patch(plt.Rectangle((j - 0.45, i - 0.45), 0.9, 0.9, fill=False, lw=2.2,
                                           ec="black"))
    ax.set_xticks(range(len(measures)), measures, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(tests)), [" · ".join(x for x in t if x) for t in tests], fontsize=8)
    scope = table.qualifier("effect_size", "EffectScope")
    pk = table.qualifier("p_value", "PKind") or "p"
    pscope = table.qualifier("p_value", "PScope")
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label(em, fontsize=8)
    width = max(30, int(9 * max(w, 4.5)))           # characters a title line can hold
    lines = [str(spec.record.get("title", spec.id)),
             f"{em}{' (' + scope + ')' if scope else ''} per test; hatched: its interval includes 0",
             f"outlined: {pk} p < {spec.alpha:g}{' (' + pscope + ')' if pscope else ''}"]
    ax.set_title("\n".join(textwrap.fill(x, width) for x in lines), fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path


def render_spec_figures(scan, staging_dir: Path, dpi: int, profile, log) -> list[FigureEntry]:
    """The overview heatmaps of every specification analysis, then the profile's figures."""
    figures = []
    sources = {(t.paradigm, t.analysis): t.source_label for t in scan.tables}
    for key, spec in scan.spec.items():
        paradigm, analysis = key
        source = sources.get(key) or next((f.source_label for f in scan.figures
                                           if (f.paradigm, f.analysis) == key), "results")
        dest = Path(staging_dir) / _slugify(source) / paradigm / analysis
        paths = []
        for k, table in enumerate(spec.tables_with_role("tests")):
            try:
                p = effect_heatmap(spec, table, dest / f"effects_{k + 1}_{_slugify(table.path.stem)}.png", dpi)
            except Exception as exc:  # noqa: BLE001
                log(f"  WARNING: effect overview failed for {spec.id}: {exc}")
                p = None
            if p:
                paths.append(p)
        try:
            paths += list(profile.render_spec(spec, dest, dpi, log))
        except Exception as exc:  # noqa: BLE001
            log(f"  WARNING: {profile.name} figures failed for {spec.id}: {exc}")
        figures += [FigureEntry(src_path=p, category="analytics", source_label=source, paradigm=paradigm,
                                analysis=analysis, filename=p.name) for p in paths]
    return figures
