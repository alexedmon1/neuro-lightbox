"""Overview figures of analyses written to the results specification.

One figure per tests table: tests (facet · contrast) by measure, each cell the
test's effect size from the column the dictionary marks ``effect_size``, labelled
with its value, outlined where the test is significant under the analysis's own
correction, and hatched where the interval includes zero. Nulls are drawn like
everything else. A profile adds its own figures (e.g. maps) through
:meth:`~neuro_lightbox.profiles.Profile.render_spec`.

Two contrasts of one facet whose effects are exact negatives on every measure are the
two one-sided tests of one comparison (A > B and B > A; mean > 0 and mean < 0). They
share a row: the first contrast's effect, outlined if either test passes, marked ▲ where
the row's own direction passes and ▼ where the opposite one does.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from .scanner import FigureEntry, _slugify
from .spec import SpecAnalysis, SpecTable, StudyNames, as_bool, as_float

#: Subgroups smaller than this are drawn hollow and do not set the axis range.
MIN_SUBGROUP_N = 3

#: Effect measures on a standardised scale (the colour scale gets a floor of 0.5).
STANDARDISED = {"d", "g", "cohen's d", "hedges' g", "r", "z", "z_diff"}


def _significant(row, std, alpha):
    if "significant" in std:
        flag = as_bool(row.get(std["significant"]))
        if flag is not None:
            return flag
    p = as_float(row.get(std.get("p_value", ""), None))
    return p is not None and p < alpha


def _pairs(keys, cell, measures, std) -> dict:
    """Second contrast -> first, for contrasts of one facet measured on the same measures
    whose effects are exact negatives on every one (the two one-sided tests of one
    comparison)."""
    partner, taken = {}, set()
    for a_i, a in enumerate(keys):
        if a in taken:
            continue
        for b in keys[a_i + 1:]:
            if b in taken or b[0] != a[0]:
                continue
            has_a = [m for m in measures if a + (m,) in cell]
            if has_a != [m for m in measures if b + (m,) in cell]:
                continue                                      # a pair covers the same measures
            shared = has_a
            vals = [(as_float(cell[a + (m,)].get(std["effect_size"])),
                     as_float(cell[b + (m,)].get(std["effect_size"]))) for m in shared]
            vals = [(x, y) for x, y in vals if x is not None and y is not None]
            if vals and all(abs(x + y) <= 1e-9 * max(1.0, abs(x)) for x, y in vals):
                partner[b] = a
                taken |= {a, b}
                break
    return partner


def _layout(spec: SpecAnalysis, table: SpecTable, names: StudyNames | None = None):
    """(measures, test rows, first -> opposite contrast, (facet, contrast, measure) -> row),
    with the two one-sided tests of a comparison sharing a row; None without effects."""
    std = table.standard()
    if "effect_size" not in std or "contrast" not in std:
        return None
    _cols, rows = table.read()
    if not rows:
        return None

    def facet_of(r):
        return r.get(std["facet"], "") if "facet" in std else ""

    def measure_of(r):
        return r.get(std["measure"], "") if "measure" in std else ""

    measures = []
    for m in spec.measures + [measure_of(r) for r in rows]:
        if m not in measures and any(measure_of(r) == m for r in rows):
            measures.append(m)
    keys, cell = [], {}
    for r in rows:
        key = (facet_of(r), r.get(std["contrast"], ""))
        if key not in keys:
            keys.append(key)
        cell[key + (measure_of(r),)] = r
    partner = _pairs(keys, cell, measures, std)               # second contrast -> first
    tests = [k for k in keys if k not in partner]
    if names is not None:                                      # the study's order, if it gives one
        tests = sorted(tests, key=lambda k: names.rank(*k))
    flipped = {v: k for k, v in partner.items()}               # first -> its opposite
    return measures, tests, flipped, cell


def _row_label(t, flipped, names: StudyNames | None = None) -> str:
    names = names or StudyNames()
    return names.label(*t) + (f"  (▼ {names.contrast(flipped[t][1])})" if t in flipped else "")


def subgroup_dots(spec: SpecAnalysis, table: SpecTable, out_path: Path, dpi: int = 150,
                  names: StudyNames | None = None) -> Path | None:
    """Each subgroup's effect beside the test's own: one panel per measure, tests as rows."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    groups, sizes = {}, {}
    for col, meta in table.columns.items():
        if isinstance(meta, dict) and meta.get("Subgroup"):
            if meta.get("Standard") == "subgroup_effect":
                groups[str(meta["Subgroup"])] = col
            elif meta.get("Standard") == "subgroup_n":
                sizes[str(meta["Subgroup"])] = col
    layout = _layout(spec, table, names)
    if not groups or layout is None:
        return None
    std = table.standard()
    measures, tests, flipped, cell = layout
    def small(r, g):                     # a subgroup too small for its effect to mean much
        n = as_float(r.get(sizes[g])) if g in sizes else None
        return n is not None and n < MIN_SUBGROUP_N

    # The axis spans the tests' own effects and the subgroups large enough to estimate one;
    # anything beyond is drawn at the edge with its value.
    vals = [as_float(r.get(std["effect_size"])) for r in cell.values()]
    vals += [as_float(r.get(c)) for r in cell.values() for g, c in groups.items() if not small(r, g)]
    vals = [abs(v) for v in vals if v is not None]
    lim = max(vals + [0.5]) * 1.12
    colours = plt.get_cmap("tab10").colors
    fig, axes = plt.subplots(1, len(measures), sharey=True,
                             figsize=(1.6 + 1.25 * len(measures), 1.3 + 0.32 * len(tests)), squeeze=False)
    for j, (ax, m) in enumerate(zip(axes[0], measures)):
        ax.axvline(0, color="#999999", lw=0.8)
        for i, t in enumerate(tests):
            r = cell.get(t + (m,))
            if r is None:
                continue
            d = as_float(r.get(std["effect_size"]))
            if d is not None:
                ax.plot([d, d], [i - 0.32, i + 0.32], color="black", lw=2)
            for k, (g, col) in enumerate(groups.items()):
                v = as_float(r.get(col))
                if v is None:
                    continue
                y, c = i + (k - (len(groups) - 1) / 2) * 0.18, colours[k % len(colours)]
                face = "none" if small(r, g) else c
                if abs(v) > lim:                 # off the axis: an arrowhead at the edge, labelled
                    edge = lim * 0.97 * np.sign(v)
                    ax.plot(edge, y, ">" if v > 0 else "<", ms=4, color=c, mfc=face)
                    ax.text(edge - np.sign(v) * lim * 0.08, y, f"{v:+.3g}", fontsize=5, color=c,
                            ha="right" if v > 0 else "left", va="center")
                else:
                    ax.plot(v, y, "o", ms=3.5, color=c, mfc=face)
        ax.set_xlim(-lim, lim)
        ax.set_title(m, fontsize=8)
        ax.tick_params(axis="x", labelsize=6)
        ax.grid(axis="y", color="#eeeeee", lw=0.5)
    axes[0][0].set_yticks(range(len(tests)), [_row_label(t, flipped, names) for t in tests], fontsize=7)
    axes[0][0].invert_yaxis()
    handles = [plt.Line2D([], [], marker="o", ls="", color=colours[k % len(colours)], label=g)
               for k, g in enumerate(groups)]
    handles.append(plt.Line2D([], [], color="black", lw=2, label="the test's own effect"))
    if sizes:
        handles.append(plt.Line2D([], [], marker="o", ls="", color="grey", mfc="none",
                                  label=f"hollow: subgroup of fewer than {MIN_SUBGROUP_N}"))
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), fontsize=7, frameon=False)
    em = table.qualifier("effect_size", "EffectMeasure") or "effect"
    sub_em = next((table.columns[c].get("EffectMeasure") for c in groups.values()), em)
    fig.suptitle(f"{spec.record.get('title', spec.id)}\neach subgroup's {sub_em} (dots) beside the "
                 f"test's own {em} (bar); rows as in the effect overview", fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path


def effect_heatmap(spec: SpecAnalysis, table: SpecTable, out_path: Path, dpi: int = 150,
                   names: StudyNames | None = None) -> Path | None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    std = table.standard()
    layout = _layout(spec, table, names)
    if layout is None:
        return None
    measures, tests, flipped, cell = layout
    mat = np.full((len(tests), len(measures)), np.nan)
    sig = np.zeros_like(mat, dtype=bool)
    sig_opposite = np.zeros_like(mat, dtype=bool)
    spans_zero = np.zeros_like(mat, dtype=bool)
    for i, key in enumerate(tests):
        for j, m in enumerate(measures):
            r = cell.get(key + (m,))
            if r is None:
                continue
            d = as_float(r.get(std["effect_size"]))
            mat[i, j] = np.nan if d is None else d
            sig[i, j] = _significant(r, std, spec.alpha)
            other = cell.get(flipped[key] + (m,)) if key in flipped else None
            sig_opposite[i, j] = other is not None and _significant(other, std, spec.alpha)
            lo = as_float(r.get(std.get("effect_ci_low", ""), None))
            hi = as_float(r.get(std.get("effect_ci_high", ""), None))
            spans_zero[i, j] = lo is not None and hi is not None and lo <= 0 <= hi

    em = table.qualifier("effect_size", "EffectMeasure") or "effect"
    standardised = em.lower() in STANDARDISED
    if standardised:
        # One scale for every measure, with a floor so a page of small d's is not
        # painted as large.
        vmax = float(np.nanmax(np.abs(mat))) if np.isfinite(mat).any() else 1.0
        vmax, shade = max(vmax, 0.5), mat
    else:
        # In each measure's own units the columns are not comparable: each is coloured
        # against its own largest |effect|; the printed values stay as they are.
        colmax = np.nanmax(np.where(np.isfinite(mat), np.abs(mat), np.nan), axis=0) \
            if np.isfinite(mat).any() else np.ones(mat.shape[1])
        colmax = np.where(np.isfinite(colmax) & (colmax > 0), colmax, 1.0)
        vmax, shade = 1.0, mat / colmax[None, :]
    w = 1.6 + 0.8 * len(measures)
    h = 1.4 + 0.36 * len(tests)
    fig, ax = plt.subplots(figsize=(max(w, 4.5), max(h, 2.2)))
    im = ax.imshow(shade, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    for i in range(len(tests)):
        for j in range(len(measures)):
            v = mat[i, j]
            paired = tests[i] in flipped
            marks = ("▲" if paired and sig[i, j] else "") + ("▼" if sig_opposite[i, j] else "")
            if np.isfinite(v):
                ax.text(j, i, f"{v:+.2g}{marks}", ha="center", va="center", fontsize=7,
                        color="white" if abs(shade[i, j]) > 0.6 * vmax else "black",
                        fontweight="bold" if sig[i, j] or sig_opposite[i, j] else "normal")
            if spans_zero[i, j]:                       # independent of significance: a test
                ax.add_patch(plt.Rectangle((j - 0.45, i - 0.45), 0.9, 0.9, fill=False, lw=0,
                                           hatch="////", ec="#999999"))
            if sig[i, j] or sig_opposite[i, j]:        # can pass while its summary effect's CI spans 0
                ax.add_patch(plt.Rectangle((j - 0.45, i - 0.45), 0.9, 0.9, fill=False, lw=2.2,
                                           ec="black"))
    ax.set_xticks(range(len(measures)), measures, rotation=45, ha="right", fontsize=8)
    labels = [_row_label(t, flipped, names) for t in tests]
    ax.set_yticks(range(len(tests)), labels, fontsize=8)
    scope = table.qualifier("effect_size", "EffectScope")
    pk = table.qualifier("p_value", "PKind") or "p"
    pscope = table.qualifier("p_value", "PScope")
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label(em if standardised else f"{em} / the measure's largest |{em}|", fontsize=8)
    width = max(30, int(9 * max(w, 4.5)))           # characters a title line can hold
    lines = [str(spec.record.get("title", spec.id)),
             f"{em}{' (' + scope + ')' if scope else ''} per test"
             + ("" if standardised else ", in each measure's own units (colour scaled per measure)")
             + "; hatched: its interval includes 0",
             f"outlined: {pk} p < {spec.alpha:g}{' (' + pscope + ')' if pscope else ''}"
             + ("; ▲ the row's own direction, ▼ the opposite one (named in the row)" if flipped else "")]
    ax.set_title("\n".join(textwrap.fill(x, width) for x in lines), fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path


def render_spec_figures(scan, staging_dir: Path, dpi: int, profile, log,
                        names: StudyNames | None = None) -> list[FigureEntry]:
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
                p = effect_heatmap(spec, table, dest / f"effects_{k + 1}_{_slugify(table.path.stem)}.png", dpi,
                                   names)
            except Exception as exc:  # noqa: BLE001
                log(f"  WARNING: effect overview failed for {spec.id}: {exc}")
                p = None
            if p:
                paths.append(p)
            try:
                p = subgroup_dots(spec, table, dest / f"subgroups_{k + 1}_{_slugify(table.path.stem)}.png", dpi,
                                  names)
            except Exception as exc:  # noqa: BLE001
                log(f"  WARNING: subgroup overview failed for {spec.id}: {exc}")
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
