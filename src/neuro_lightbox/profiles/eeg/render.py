"""The EEG profile's overview figures: source-analytics stat tables, drawn.

Column-driven renderers over source-analytics' native hypothesis schema
(``hypothesis``, ``band``, ``spatial``, ``dv``, ``effect_size``, ``stat``,
``q_value``; the legacy aliases are still read), the frequency-band order, the
filename conventions that rank an analysis's tables, and the source-analytics
helpers drawn beside or instead of the overview: connectivity circos and ROI
brain mosaics (:mod:`.circos`, :mod:`.brain_mosaic`), and the nodal graph-metric
maps next to the NBS view. See :mod:`neuro_lightbox.render` for the shared
machinery.
"""

from __future__ import annotations

from pathlib import Path

from ...manifest import _read_csv
from ...render import (  # noqa: F401  (re-exported for the digest builders)
    Renderer,
    _any,
    _bar,
    _has,
    _heatmap,
    _pick_preferred,
    _records,
    _to_float,
    _unique,
    relabel,
)
from ...render import _grid as _core_grid
from ...render import render_table_figures as _render_table_figures
from ...render import select_renderer as _select_renderer
from ...scanner import _slugify

# Canonical Jonak-style band order; categories not in this list keep file order.
BAND_ORDER = ["Delta", "Theta", "Alpha", "Beta", "Low Gamma", "High Gamma", "Epsilon"]

# Columns scanned, in precedence order, to decide significance of a row.
# Corrected columns (q/FDR) precede raw p so a row is judged on the strictest
# available threshold.
_SIG_PVAL_COLS = ("q_value", "group_q", "p_corrected", "p_fdr", "p_value", "p")

# Per-unit raw tables (one row per vertex) must not be force-fit into a
# contrast x band heatmap — their summaries live in dedicated *_summary tables.
_PER_VERTEX_COLS = ("vertex_idx", "vertex")

# A measure/dv column that an overview figure facets on; in overview mode we
# render only the single preferred value below.
_FACET_COLS = ("metric", "dv", "power_type")
_FACET_PREF = ("relative", "coherence", "exponent", "te", "absolute")

# Preferred contrast for a single-contrast overview (e.g. per-ROI maps).
_CONTRAST_PREF = ("disease", "rescue")

# Preferred connectivity metric to feature when a table spans several of them
# (the nodal graph-metric table carries all five); imag_coherence is the study's
# primary metric, matched before the substring-y "coherence".
_CONN_METRIC_PREF = ("imag_coherence", "coherence", "dwpli", "pli", "aec")



# Legacy hypothesis-CSV alias -> native column. Emitted by source-analytics'
# ``.add_legacy_aliases`` (R) / ``tabular.py`` (Python) during the schema
# migration; ``_to_native`` lets renderers read the native schema whether or not
# the source table still carries the aliases. Drop this once the aliases are gone.
_ALIAS_TO_NATIVE = {
    "contrast": "hypothesis",
    "roi": "spatial",
    "power_type": "dv",
    "t_ratio": "stat",
    "t": "stat",
    "hedges_g": "effect_size",
    "p_fdr": "q_value",
}


def _to_native(records: list[dict]) -> list[dict]:
    """Fill missing native columns from legacy aliases (dual-read). Mutates and
    returns ``records`` so downstream reads can use the native schema."""
    for rec in records:
        for alias, native in _ALIAS_TO_NATIVE.items():
            if rec.get(native) in (None, "") and rec.get(alias) not in (None, ""):
                rec[native] = rec[alias]
    return records


def _is_sig(rec: dict) -> bool:
    """Significance of a row: explicit flag, else first p/q column < 0.05."""
    flag = rec.get("significant")
    if flag not in (None, ""):
        return str(flag).strip().upper() in ("TRUE", "1", "YES", "T")
    for col in _SIG_PVAL_COLS:
        if rec.get(col) not in (None, ""):
            f = _to_float(rec[col])
            if f is not None:
                return f < 0.05
    return False


def _order_categories(cats: list[str], key: str) -> list[str]:
    """Apply canonical band order when the axis is a band; else keep order."""
    if key != "band":
        return cats
    known = [b for b in BAND_ORDER if b in cats]
    extra = [c for c in cats if c not in BAND_ORDER]
    return known + extra


def _facet_column(headers, records):
    """Return (column, values) of the first present measure/dv facet column."""
    for c in _FACET_COLS:
        if c in headers:
            vals = _unique(records, c)
            if vals:
                return c, vals
    return None, [None]


def _grid(records, row_key, col_key, value_fn, sig_fn=_is_sig, agg="last"):
    """The shared grid, with bands in canonical order and rows judged by _is_sig."""
    return _core_grid(records, row_key, col_key, value_fn, sig_fn, agg,
                      order=_order_categories)


def _facet_heatmaps(records, headers, out_dir, stem, dpi, value_fn, *,
                    col_key, sig_fn=_is_sig, agg="last", center=0.0,
                    value_label="Hedges g", cmap="RdBu_r", suffix="effect_size",
                    single=False):
    """Emit contrast x ``col_key`` heatmap(s), faceted by the measure column.

    With ``single=True`` (overview mode) only the preferred facet value is drawn,
    giving exactly one figure.
    """
    records = _to_native(records)
    fcol, fvals = _facet_column(headers, records)
    if single and fcol:
        fvals = [_pick_preferred(fvals, _FACET_PREF)]
    out = []
    for fval in fvals:
        subset = records if fcol is None else [r for r in records if r.get(fcol) == fval]
        mat, rows, cols, smask = _grid(subset, "hypothesis", col_key, value_fn, sig_fn, agg)
        if not rows or not cols:
            continue
        title = stem + (f" — {fval}" if fval else "")
        fname = f"{stem}__{suffix}" + (f"_{_slugify(fval)}" if fval else "") + ".png"
        path = out_dir / fname
        _heatmap(mat, rows, cols, smask, title, path, dpi,
                 center=center, value_label=value_label, cmap=cmap)
        out.append(path)
    return out


# --------------------------------------------------------------------------- #
# Renderers (first match in REGISTRY wins). Each render() honors overview=True
# by returning exactly one figure.
# --------------------------------------------------------------------------- #
class RoiBandHeatmap(Renderer):
    """Per-ROI effect-size map: one ROI x band heatmap per contrast."""

    name = "roi_band_heatmap"

    @staticmethod
    def matches(headers):
        if "graph_metric" in headers:   # nodal graph tables have their own renderer
            return False
        return (_any(headers, "hypothesis", "contrast")
                and _any(headers, "spatial", "roi")
                and "band" in headers
                and _any(headers, "effect_size", "hedges_g"))

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        records = _to_native(records)
        contrasts = _unique(records, "hypothesis")
        if overview and contrasts:
            contrasts = [_pick_preferred(contrasts, _CONTRAST_PREF)]
        out = []
        for contrast in contrasts:
            subset = [r for r in records if r.get("hypothesis") == contrast]
            mat, rows, cols, smask = _grid(
                subset, "spatial", "band", lambda r: _to_float(r.get("effect_size"))
            )
            if not rows or not cols:
                continue
            path = out_dir / f"{stem}__{_slugify(contrast)}.png"
            _heatmap(mat, rows, cols, smask, f"{stem} — {contrast}", path, dpi,
                     value_label="Hedges g")
            out.append(path)
        return out


class RoiGraphMetricHeatmap(Renderer):
    """Nodal graph-metric group differences: one ROI x band heatmap of the Welch
    t-statistic per graph metric (degree / clustering / betweenness), at the
    primary connectivity metric and contrast. ★ marks FDR-significant ROIs.

    This is the *nodal* companion to the NBS subnetwork view: both summarize the
    same connectivity matrices, so it renders alongside the NBS overview in the
    Connectivity -> Network section rather than replacing it. The table spans all
    contrasts x 5 connectivity metrics x 3 graph metrics; the overview collapses
    to one connectivity metric and (in overview mode) one contrast, leaving the
    full grid to the sortable CSV.
    """

    name = "roi_graph_metric_heatmap"

    @staticmethod
    def matches(headers):
        return (_any(headers, "hypothesis", "contrast")
                and _any(headers, "spatial", "roi")
                and _has(headers, "band", "graph_metric")
                and _any(headers, "stat", "t"))

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        def sig_fn(rec):
            f = _to_float(rec.get("q_value"))
            return f is not None and f < 0.05

        # Nodal rows only: the native hypotheses table also carries the global
        # (whole-network) metrics with an empty spatial cell.
        records = [r for r in _to_native(records) if r.get("spatial") not in (None, "")]

        # Feature one connectivity metric (the table carries all five).
        conn_vals = _unique(records, "conn_metric")
        conn = _pick_preferred(conn_vals, _CONN_METRIC_PREF) if conn_vals else None
        recs = [r for r in records if r.get("conn_metric") == conn] if conn else records

        contrasts = _unique(recs, "hypothesis")
        if overview and contrasts:
            contrasts = [_pick_preferred(contrasts, _CONTRAST_PREF)]

        out = []
        for contrast in contrasts:
            csub = [r for r in recs if r.get("hypothesis") == contrast]
            for gm in _unique(csub, "graph_metric"):
                subset = [r for r in csub if r.get("graph_metric") == gm]
                mat, rows, cols, smask = _grid(
                    subset, "spatial", "band", lambda r: _to_float(r.get("stat")), sig_fn=sig_fn,
                )
                if not rows or not cols:
                    continue
                cm = f" · {conn}" if conn else ""
                title = f"{stem} — {gm} · {contrast}{cm}"
                fname = f"{stem}__{_slugify(gm)}_{_slugify(contrast)}.png"
                path = out_dir / fname
                _heatmap(mat, rows, cols, smask, title, path, dpi,
                         value_label="Welch t (A − B); ★ FDR<0.05")
                out.append(path)
        return out


class MvpaHeatmap(Renderer):
    """Per-band decoding strength as a contrast x band heatmap (centered at chance)."""

    name = "mvpa_heatmap"

    @staticmethod
    def matches(headers):
        return (
            "band" in headers
            and _any(headers, "auc", "accuracy")
            and _any(headers, "ci_lower", "ci_upper")
        )

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        metric = "auc" if "auc" in headers else "accuracy"
        return _facet_heatmaps(
            records, headers, out_dir, stem, dpi,
            value_fn=lambda r: _to_float(r.get(metric)),
            col_key="band", center=0.5, value_label=metric.upper(),
            cmap="RdBu_r", suffix="mvpa", single=overview,
        )


def _parse_nbs_key(key: str):
    """Split an NBS key ``<contrast>_<band>[_<metric>]`` into its parts.

    The key joins fields with ``_`` but bands themselves contain spaces
    ("Low Gamma"), so we locate a known band token rather than naive splitting.
    Returns ``(contrast, band, metric)`` or ``(None, None, None)``.
    """
    for band in sorted(BAND_ORDER + ["Epsilon"], key=len, reverse=True):
        marker = "_" + band
        idx = key.find(marker)
        if idx < 0:
            continue
        rest = key[idx + len(marker):]
        if rest == "" or rest.startswith("_"):
            return key[:idx], band, (rest[1:] if rest.startswith("_") else "")
    return None, None, None


class NbsComponentPlot(Renderer):
    """Network-Based Statistic as a contrast x band heatmap of the largest
    significant component's size, faceted by connectivity metric."""

    name = "nbs_heatmap"
    # NBS is the network module's primary figure and lives on its own
    # (Connectivity → Network) section, so it shows every connectivity metric
    # rather than collapsing to one canonical overview facet.
    full_set = True

    @staticmethod
    def matches(headers):
        return _has(headers, "key", "component", "n_edges", "p_corrected")

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        labels = contrast_labels or {}
        # Parse keys into contrast/band/metric; keep the largest component per cell.
        parsed = []
        for rec in records:
            key = rec.get("key")
            if not key:
                continue
            contrast, band, metric = _parse_nbs_key(str(key))
            if contrast is None:
                continue
            parsed.append({
                "contrast": labels.get(contrast, contrast),
                "band": band,
                "metric": metric,
                "n_edges": rec.get("n_edges"),
                "p_corrected": rec.get("p_corrected"),
            })

        if not parsed:  # unparseable keys → fall back to the per-key bar chart
            largest: dict[str, dict] = {}
            for rec in records:
                key = rec.get("key")
                if key in (None, ""):
                    continue
                n = _to_float(rec.get("n_edges")) or 0.0
                if key not in largest or n > (_to_float(largest[key].get("n_edges")) or 0.0):
                    largest[key] = rec
            if not largest:
                return []
            keys = list(largest.keys())
            path = out_dir / f"{stem}__nbs.png"
            _bar(keys, [_to_float(largest[k].get("n_edges")) or 0.0 for k in keys],
                 [_is_sig(largest[k]) for k in keys], f"{stem} — largest component / key",
                 "n_edges", path, dpi)
            return [path]

        metrics = _unique(parsed, "metric") or [None]
        out = []
        for metric in metrics:
            subset = parsed if metric in (None, "") else [r for r in parsed if r.get("metric") == metric]
            mat, rows, cols, smask = _grid(
                subset, "contrast", "band",
                lambda r: _to_float(r.get("n_edges")), sig_fn=_is_sig, agg="max_abs",
            )
            if not rows or not cols:
                continue
            title = stem + (f" — {metric}" if metric else "")
            fname = f"{stem}__nbs" + (f"_{_slugify(metric)}" if metric else "") + ".png"
            path = out_dir / fname
            _heatmap(mat, rows, cols, smask, title, path, dpi,
                     value_label="largest component (edges); ★ p<0.05",
                     cmap="Blues", vmin=0, int_annot=True)
            out.append(path)
            if overview:
                break
        return out


class ClusterHeatmap(Renderer):
    """Cluster strength as a contrast x band heatmap (signed max-magnitude stat)."""

    name = "cluster_heatmap"

    @staticmethod
    def matches(headers):
        return _has(headers, "band", "cluster_stat", "p_corrected")

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        return _facet_heatmaps(
            records, headers, out_dir, stem, dpi,
            value_fn=lambda r: _to_float(r.get("cluster_stat")),
            col_key="band", agg="max_abs", value_label="cluster stat",
            suffix="cluster", single=overview,
        )


class SummaryHeatmap(Renderer):
    """Effect-size summary as a contrast x band heatmap, per metric facet."""

    name = "summary_heatmap"

    @staticmethod
    def matches(headers):
        return _has(headers, "band", "max_abs_hedges_g")

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        def sig_fn(rec):
            if "n_nominal_sig" in rec:
                return (_to_float(rec.get("n_nominal_sig")) or 0) > 0
            return _is_sig(rec)

        return _facet_heatmaps(
            records, headers, out_dir, stem, dpi,
            value_fn=lambda r: _to_float(r.get("max_abs_hedges_g")),
            col_key="band", sig_fn=sig_fn, value_label="max |Hedges g|",
            cmap="Reds", center=0.0, suffix="summary", single=overview,
        )


class EffectSizeHeatmap(Renderer):
    """Contrast x band (or freq_pair) effect-size heatmap; faceted by metric.

    The general-purpose choice for clean one-row-per-cell effect-size tables.
    Skips per-vertex raw tables (their summaries are handled elsewhere).
    """

    name = "effect_size_heatmap"

    @staticmethod
    def matches(headers):
        if _any(headers, *_PER_VERTEX_COLS):
            return False
        return (
            _any(headers, "effect_size", "hedges_g")
            and _any(headers, "hypothesis", "contrast")
            and _any(headers, "band", "freq_pair")
        )

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        records = _to_native(records)
        col_key = "band" if "band" in headers else "freq_pair"
        return _facet_heatmaps(
            records, headers, out_dir, stem, dpi,
            value_fn=lambda r: _to_float(r.get("effect_size")),
            col_key=col_key, suffix="effect_size", single=overview,
        )


# Order matters: more specific renderers first.
REGISTRY: list[type[Renderer]] = [
    RoiBandHeatmap,
    RoiGraphMetricHeatmap,
    MvpaHeatmap,
    NbsComponentPlot,
    ClusterHeatmap,
    SummaryHeatmap,
    EffectSizeHeatmap,
]


def select_renderer(headers: list[str]) -> type[Renderer] | None:
    """Return the first registered renderer whose column requirements match."""
    return _select_renderer(headers, REGISTRY)


# --------------------------------------------------------------------------- #
# Module-level overview selection
# --------------------------------------------------------------------------- #
def _table_priority(filename: str) -> int:
    """Rank tables so the overview prefers global effect-size summaries over
    per-unit detail (ROI / vertex / directional) tables."""
    f = filename.lower()
    if "posthoc_global" in f:
        return 100
    if "_global" in f or f.endswith("global.csv"):
        return 90
    if "effect_size_summary" in f:
        return 75
    if "mvpa" in f:
        return 70
    if "nbs" in f:
        return 65
    if "cluster_results" in f:
        return 60
    if "summary" in f:
        return 55
    if "posthoc_region" in f:
        return 40
    if _any([f], "posthoc_roi", "voxelwise", "directional"):  # per-unit detail
        return 10
    return 30


def _connectivity_edges_csv(analytics_dir: Path, paradigm: str, analysis: str) -> Path | None:
    """The per-subject connectivity edge table an NBS module was computed from.

    source-analytics keeps it in the working tree: the module's own
    ``data/<analysis>_edges.csv`` or, for the graph/NBS modules that consume
    roi_connectivity's matrices, ``roi_connectivity/data/roi_connectivity_edges.csv``.
    """
    candidates = [
        analytics_dir / paradigm / analysis / "data" / f"{analysis}_edges.csv",
        analytics_dir / paradigm / "roi_connectivity" / "data" / "roi_connectivity_edges.csv",
        analytics_dir / paradigm / "roi_connectivity" / "data" / "connectivity_edges.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _roi_posthoc_table(group):
    """The per-ROI posthoc table in a module group, if present (for brain mosaics)."""
    for tbl in group:
        if "posthoc_roi" in tbl.filename.lower():
            return tbl
    return None


def _analysis_key(analysis: str) -> str:
    """Strip a leading ``roi_`` so 'roi_psd' -> 'psd' for ANALYSIS_CMAPS lookup."""
    return analysis[4:] if analysis.startswith("roi_") else analysis


# --------------------------------------------------------------------------- #
# Hooks around the overview (see neuro_lightbox.profiles.Profile)
# --------------------------------------------------------------------------- #
def render_state(brain=None, circos=None, contrast_labels=None, log=lambda *a, **k: None):
    """What the hooks below need for one build.

    ``brain`` is an optional dict: ``{categories, contrasts, python, power_type}``
    (``categories`` may be None — the worker then auto-picks the bundled atlas
    file). ``circos`` is ``{analytics_dir, contrasts, labels, metrics, python}``.
    Brain mosaics and circos are optional and require source-analytics: each is
    probed once here, and a missing interpreter is reported once.
    """
    brain_ok = False
    if brain:
        from . import brain_mosaic

        brain_ok = brain_mosaic.brain_available(brain.get("python"))
        if not brain_ok:
            log("  WARNING: brain mosaics unavailable — source-analytics interpreter not "
                f"usable at {brain_mosaic.resolve_python(brain.get('python'))}; using heatmaps")

    circos_ok = False
    if circos and circos.get("contrasts"):
        from . import circos as circos_mod

        circos_ok = circos_mod.circos_available(circos.get("python"))
        if not circos_ok:
            log("  WARNING: circos unavailable — source-analytics interpreter not usable "
                f"at {circos_mod._resolve(circos.get('python'))}")
    return {"brain": brain, "brain_ok": brain_ok, "circos": circos, "circos_ok": circos_ok,
            "contrast_labels": contrast_labels}


def render_before(group, dest: Path, module: tuple, state, log) -> tuple[list, bool]:
    """Circos beside the overview; brain mosaics instead of it."""
    state = state or {}
    _source, paradigm, analysis = module
    paths_out: list[Path] = []

    # 0. Connectivity circos: significance chord diagrams (ROIs grouped by
    #    region) for NBS modules, gated on the FDR-significant subnetworks in
    #    the module's *_subnetwork_edges.csv (written by source-analytics next
    #    to its hypotheses table). They render ALONGSIDE the module's overview
    #    (the NBS component heatmap), not instead of it.
    circos = state.get("circos")
    if state.get("circos_ok"):
        from . import circos as circos_mod

        sub_tbl = next((t for t in group if t.filename.lower().endswith("_subnetwork_edges.csv")), None)
        if sub_tbl is not None:
            edges_csv = _connectivity_edges_csv(Path(circos["analytics_dir"]), paradigm, analysis)
            if edges_csv is None:
                log(f"  WARNING: circos skipped for {paradigm}/{analysis}: no connectivity "
                    f"edge CSV under {Path(circos['analytics_dir']) / paradigm}")
            else:
                dest.mkdir(parents=True, exist_ok=True)
                paths_out += circos_mod.render_circos(
                    edges_csv, sub_tbl.src_path, dest, circos["contrasts"],
                    metrics=circos.get("metrics"),
                    labels=circos.get("labels"), python_path=circos.get("python"), log=log,
                    categories=circos.get("categories"), atlas=circos.get("atlas"),
                )

    # 1. Brain mosaics for ROI posthoc modules (replace the flat overview).
    brain = state.get("brain")
    if state.get("brain_ok"):
        from . import brain_mosaic

        roi_tbl = _roi_posthoc_table(group)
        if roi_tbl is not None:
            dest.mkdir(parents=True, exist_ok=True)
            paths = brain_mosaic.render_roi_mosaics(
                roi_tbl.src_path,
                categories=brain["categories"],
                out_dir=dest,
                analysis_name=_analysis_key(analysis),
                contrasts=brain.get("contrasts"),
                labels=brain.get("labels"),
                power_type=brain.get("power_type", "relative"),
                atlas=brain.get("atlas"),
                python_path=brain.get("python"),
                log=log,
            )
            if paths:
                return paths_out + list(paths), True  # mosaics stand in for the overview
    return paths_out, False


def render_after(ranked, chosen, renderer, dest: Path, module: tuple, state, dpi, log) -> list:
    """Nodal graph metrics render ALONGSIDE the chosen overview: the network
    module shows both the NBS subnetwork view and the nodal graph-metric maps of
    the same connectivity matrices. (When the graph table is the only renderable
    one it is already the chosen overview — skip it here so it isn't drawn twice.)"""
    contrast_labels = (state or {}).get("contrast_labels")
    graph_done = renderer is RoiGraphMetricHeatmap
    for tbl2 in ranked:
        if graph_done or (chosen is not None and tbl2 is chosen[0]):
            continue
        try:
            data2 = _read_csv(tbl2.src_path)
        except Exception:  # noqa: BLE001
            continue
        if select_renderer(data2["headers"]) is not RoiGraphMetricHeatmap:
            continue
        graph_done = True  # native hypotheses + legacy stats: draw the first only
        records2 = relabel(_records(data2["headers"], data2["rows"]),
                           ("contrast", "hypothesis"), contrast_labels)
        dest.mkdir(parents=True, exist_ok=True)
        stem2 = Path(tbl2.filename).stem
        try:
            return RoiGraphMetricHeatmap.render(
                records2, data2["headers"], dest, stem2, dpi,
                overview=True, contrast_labels=contrast_labels,
            )
        except Exception as exc:  # noqa: BLE001
            log(f"  WARNING: render failed {tbl2.filename} [graph metrics]: {exc}")
            continue
    return []


def render_table_figures(tables, staging_dir, dpi: int = 150, log=lambda *a, **k: None,
                         brain=None, circos=None, contrast_labels=None):
    """Render figures per analysis module, as the EEG profile draws them.

    Tables are grouped by ``(source_label, paradigm, analysis)``. For ROI modules
    with a per-ROI posthoc table, anatomy-aware brain mosaics are rendered (when
    ``brain`` is configured and source-analytics is available); otherwise the
    module gets a single flat overview figure from its highest-priority table.
    ``brain`` and ``circos`` are as in :func:`render_state`.

    Returns a list of :class:`~neuro_lightbox.scanner.FigureEntry`
    (category ``"analytics"``).
    """
    from ...profiles import get_profile

    return _render_table_figures(
        tables, staging_dir, dpi, log, profile=get_profile("eeg"),
        state=render_state(brain, circos, contrast_labels, log),
        contrast_labels=contrast_labels)
