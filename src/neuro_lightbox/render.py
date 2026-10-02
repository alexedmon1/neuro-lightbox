"""Render one overview figure per analysis from its tables, at build time.

Philosophy: **one canonical overview figure per analysis module**. For each
``(source, paradigm, analysis)`` group the profile ranks the tables
(:meth:`~neuro_lightbox.profiles.Profile.table_priority`) and the first one a
renderer matches is drawn — typically a contrast x category heatmap of the
primary effect. This keeps a gallery to a handful of figures a reader can
actually absorb, while staying fully automatic.

Renderers are *column-driven*: each declares which columns it needs
(``matches``) rather than keying off a module name; the profile lists them
(:attr:`~neuro_lightbox.profiles.Profile.renderers`). A module whose tables match
no renderer simply contributes no figure — its tables still appear in the
gallery as sortable CSVs. Rendering never aborts the build: per-table failures
are caught and logged by :func:`render_table_figures`.

This module holds what every profile's renderers share: parsing helpers, the
grid and heatmap / bar primitives, the renderer base class, and the per-module
orchestration with the profile's hooks before and after the overview.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: no display, safe under any build environment

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .manifest import _read_csv  # noqa: E402
from .scanner import FigureEntry, _slugify  # noqa: E402


# --------------------------------------------------------------------------- #
# Small parsing / lookup helpers
# --------------------------------------------------------------------------- #
def _to_float(value) -> float | None:
    """Parse a CSV cell to float, returning None for blanks / NA / NaN."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _records(headers: list[str], rows: list[list[str]]) -> list[dict]:
    """Turn parallel headers/rows into a list of column->value dicts."""
    return [dict(zip(headers, r)) for r in rows]


def _has(headers: list[str], *cols: str) -> bool:
    return all(c in headers for c in cols)


def _any(headers: list[str], *cols: str) -> bool:
    return any(c in headers for c in cols)


def _unique(records: list[dict], key: str) -> list[str]:
    """Distinct non-empty values of ``key`` in first-seen order."""
    seen: list[str] = []
    for rec in records:
        v = rec.get(key)
        if v not in (None, "") and v not in seen:
            seen.append(v)
    return seen


def _pick_preferred(values, prefs):
    """First value whose lowercased text contains a preference, else the first."""
    for pref in prefs:
        for v in values:
            if pref in str(v).lower():
                return v
    return values[0] if values else None


# --------------------------------------------------------------------------- #
# Shared drawing primitives
# --------------------------------------------------------------------------- #
def _grid(records, row_key, col_key, value_fn, sig_fn=None, agg="last", order=None):
    """Build a (values, rows, cols, sig_mask) grid from long-format records.

    agg="last" keeps the final value per cell (clean one-row-per-cell tables);
    agg="max_abs" keeps the largest-magnitude value and ORs significance across
    all rows mapping to that cell (e.g. multiple clusters per category).
    ``order(cols, col_key)`` puts the columns in the profile's order (default:
    first seen); ``sig_fn`` marks a cell significant (default: never).
    """
    sig_fn = sig_fn or (lambda rec: False)
    rows: list[str] = []
    cols: list[str] = []
    val: dict[tuple[str, str], float] = {}
    sig: dict[tuple[str, str], bool] = {}
    for rec in records:
        r, c = rec.get(row_key), rec.get(col_key)
        if r in (None, "") or c in (None, ""):
            continue
        v = value_fn(rec)
        if v is None:
            continue
        if r not in rows:
            rows.append(r)
        if c not in cols:
            cols.append(c)
        key = (r, c)
        if agg == "max_abs":
            if key not in val or abs(v) > abs(val[key]):
                val[key] = v
            sig[key] = sig.get(key, False) or sig_fn(rec)
        else:
            val[key] = v
            sig[key] = sig_fn(rec)

    if order is not None:
        cols = order(cols, col_key)
    mat = np.full((len(rows), len(cols)), np.nan)
    smask = np.zeros((len(rows), len(cols)), dtype=bool)
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            if (r, c) in val:
                mat[i, j] = val[(r, c)]
                smask[i, j] = sig[(r, c)]
    return mat, rows, cols, smask


def _heatmap(mat, rows, cols, smask, title, out_path, dpi,
             center=0.0, value_label="value", cmap="RdBu_r",
             vmin=None, vmax=None, int_annot=False):
    """Heatmap with significance stars.

    Diverging around ``center`` by default; pass ``vmin``/``vmax`` for a fixed
    (e.g. sequential) scale. ``int_annot`` formats cell labels as integers.
    """
    n_r, n_c = mat.shape
    fig, ax = plt.subplots(figsize=(max(4.0, 0.65 * n_c + 2.5), max(2.5, 0.45 * n_r + 1.4)))
    finite = mat[np.isfinite(mat)]
    if vmin is not None or vmax is not None:
        lo = vmin if vmin is not None else (float(np.min(finite)) if finite.size else 0.0)
        hi = vmax if vmax is not None else (float(np.max(finite)) if finite.size else 1.0)
        if hi <= lo:
            hi = lo + 1.0
    else:
        dev = float(np.max(np.abs(finite - center))) if finite.size else 1.0
        dev = dev or 1.0
        lo, hi = center - dev, center + dev
    im = ax.imshow(mat, cmap=cmap, vmin=lo, vmax=hi, aspect="auto")
    ax.set_xticks(range(n_c))
    ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(n_r))
    ax.set_yticklabels(rows, fontsize=8)
    for i in range(n_r):
        for j in range(n_c):
            if np.isfinite(mat[i, j]):
                v = mat[i, j]
                label = (f"{int(round(v))}" if int_annot else f"{v:.2f}") + ("★" if smask[i, j] else "")
                frac = (v - lo) / (hi - lo) if hi > lo else 0.0
                ax.text(
                    j, i, label, ha="center", va="center", fontsize=7,
                    color="white" if frac > 0.62 else "black",
                )
    ax.set_title(title, fontsize=10)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(value_label, fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def _bar(labels, values, sig_flags, title, ylabel, out_path, dpi, baseline=None):
    """Bar chart; significant bars in crimson, others steel-blue."""
    fig, ax = plt.subplots(figsize=(max(4.0, 0.5 * len(labels) + 2.0), 3.4))
    colors = ["#c0392b" if s else "#4a78b5" for s in sig_flags]
    ax.bar(range(len(labels)), values, color=colors)
    if baseline is not None:
        ax.axhline(baseline, color="gray", ls="--", lw=1)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Renderers. Each render() honors overview=True by returning exactly one figure.
# --------------------------------------------------------------------------- #
class Renderer:
    name = "base"
    #: Draw every facet even as an analysis's overview (a renderer whose figure
    #: set is the analysis's primary result, not a summary of it).
    full_set = False

    @staticmethod
    def matches(headers: list[str]) -> bool:  # pragma: no cover - overridden
        return False

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):  # pragma: no cover
        return []


def select_renderer(headers: list[str], registry) -> type[Renderer] | None:
    """Return the first renderer in ``registry`` whose column requirements match."""
    for renderer in registry:
        if renderer.matches(headers):
            return renderer
    return None


def relabel(records: list[dict], columns, labels: dict | None) -> list[dict]:
    """Replace contrast names in ``columns`` with the study's labels (in place)."""
    if labels:
        for rec in records:
            for key in columns:
                if rec.get(key) in labels:
                    rec[key] = labels[rec[key]]
    return records


# --------------------------------------------------------------------------- #
# Module-level overview selection
# --------------------------------------------------------------------------- #
def render_table_figures(tables, staging_dir, dpi: int = 150, log=lambda *a, **k: None, *,
                         profile, state=None, contrast_labels=None):
    """Render figures per analysis module.

    Tables are grouped by ``(source_label, paradigm, analysis)``. For each group
    the profile may draw figures first (:meth:`~Profile.render_before`) and say
    they replace the overview; otherwise the module gets one overview figure
    from its highest-ranked table a renderer matches, then whatever the profile
    draws alongside it (:meth:`~Profile.render_after`). ``state`` is what
    :meth:`~Profile.render_setup` returned.

    Returns a list of :class:`~neuro_lightbox.scanner.FigureEntry`
    (category ``"analytics"``).
    """
    staging = Path(staging_dir)

    # Group tables by module.
    modules: dict[tuple[str, str, str], list] = {}
    for tbl in tables:
        modules.setdefault((tbl.source_label, tbl.paradigm, tbl.analysis), []).append(tbl)

    figures: list[FigureEntry] = []
    for module, group in modules.items():
        source, paradigm, analysis = module
        dest = staging / _slugify(source) / paradigm / analysis

        def entries(paths):
            return [FigureEntry(src_path=path, category="analytics", source_label=source,
                                paradigm=paradigm, analysis=analysis, filename=path.name)
                    for path in paths]

        before, replaces = profile.render_before(group, dest, module, state, log)
        figures.extend(entries(before))
        if replaces:
            continue

        # The overview: the highest-priority table a renderer matches.
        ranked = sorted(group, key=lambda t: profile.table_priority(t.filename), reverse=True)

        chosen = None
        for tbl in ranked:
            try:
                data = _read_csv(tbl.src_path)
            except Exception as exc:  # noqa: BLE001
                log(f"  WARNING: render skipped (unreadable) {tbl.src_path}: {exc}")
                continue
            if select_renderer(data["headers"], profile.renderers) is not None:
                chosen = (tbl, data)
                break
        if chosen is None:
            continue

        tbl, data = chosen
        renderer = select_renderer(data["headers"], profile.renderers)
        records = relabel(_records(data["headers"], data["rows"]),
                          profile.contrast_columns, contrast_labels)
        dest.mkdir(parents=True, exist_ok=True)
        stem = Path(tbl.filename).stem
        try:
            paths = renderer.render(records, data["headers"], dest, stem, dpi,
                                    overview=not renderer.full_set,
                                    contrast_labels=contrast_labels)
        except Exception as exc:  # noqa: BLE001
            log(f"  WARNING: render failed {tbl.filename} [{renderer.name}]: {exc}")
            continue
        figures.extend(entries(paths))
        figures.extend(entries(profile.render_after(ranked, chosen, renderer, dest, module,
                                                    state, dpi, log)))
    return figures
