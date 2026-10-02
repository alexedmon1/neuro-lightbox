"""The EEG profile's digests: each comparison's result, from source-analytics tables.

The verbose ``ANALYSIS_SUMMARY.md`` that source-analytics writes is a full report,
not a summary. Instead of embedding it verbatim, we derive a short, scannable
digest directly from a module's tables: for every comparison the study ran, what
was found — magnitude, measure, direction, and the correction behind its
significance — and, where nothing reached the threshold, the largest effect
there was. Comparisons appear in the study config's order, every one of them.

What a table records about its numbers is read by :mod:`.reading` (effect
measure, correction, test kind, groups); the words come from
:mod:`neuro_lightbox.contract`, and anything a table does not record is said to
be not recorded. Per-element tables (``roi``/``vertex_idx``) are aggregated to
one entry per (contrast, category) with a count and the strongest effect, so a
30k-row table still renders a few chips. NBS component tables
(``*_nbs_results.csv``) get a dedicated sub-network digest. The shared framework
— tier sections, role badges — is :mod:`neuro_lightbox.summarize`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from ...contract import (
    arrow,
    correction_statement,
    direction_text,
    effect_text,
    number,
    p_text,
)
from ...summarize import _render_body, build_digest
from . import reading as R
from .render import (
    _facet_column,
    _is_sig,
    _parse_nbs_key,
    _records,
    _table_priority,
    _to_float,
    _to_native,
    _unique,
)

# Effect columns in priority order: (column, signed). ``signed`` effects get a
# direction arrow (▲/▼); unsigned effects (decoding metrics) are read against
# chance. A row's own effect_size_type can make an effect unsigned (omnibus).
_EFFECT_COLS = (
    ("hedges_g", True),
    ("effect_size", True),   # native: its measure is the row's effect_size_type
    ("coefficient", True),
    ("auc", False),
    ("accuracy", False),
)


def _effect_column(headers: list[str]):
    """Return (column, signed) for the first present effect column."""
    for col, signed in _EFFECT_COLS:
        if col in headers:
            return col, signed
    return None


def _element_column(headers: list[str]) -> str | None:
    """Per-element axis (``roi``/``vertex_idx``) that must be aggregated away."""
    for col in ("roi", "spatial", "vertex_idx"):
        if col in headers:
            return col
    return None

def _summary_table(tables: list[dict]) -> dict | None:
    """Pick the highest-priority table suitable for an effect digest: needs a
    ``contrast`` column, a category axis, and any recognized effect column."""
    candidates = [
        t for t in tables
        if ("contrast" in t["headers"] or "hypothesis" in t["headers"])
        and _category_column(t["headers"], _records(t["headers"], t["rows"])) is not None
        and _effect_column(t["headers"]) is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda t: _table_priority(t["filename"]))

def _nbs_table(tables: list[dict]) -> dict | None:
    """Pick an NBS component-results table (key/component/n_edges/p_corrected)."""
    for t in tables:
        h = t["headers"]
        if "key" in h and "p_corrected" in h and "n_edges" in h:
            return t
    return None

_GRAPH_METRIC_LABEL = {
    "global_efficiency": "global efficiency",
    "characteristic_path_length": "char. path length",
    "mean_clustering": "mean clustering",
    "mean_local_efficiency": "local efficiency",
    "small_worldness": "small-worldness",
    "modularity": "modularity",
    "transitivity": "transitivity",
    "assortativity": "assortativity",
}

_GRAPH_BAND_ORDER = ["Delta", "Theta", "Alpha", "Beta", "Low Gamma", "High Gamma", "Epsilon"]

def _comparison_table(tables: list[dict]) -> dict | None:
    """A source-vs-sensor comparison table (electrode_comparison): per band/dv ×
    contrast, a concordance ``correlation_r`` plus ``source_hedges_g`` /
    ``electrode_hedges_g`` with CIs."""
    cands = [t for t in tables
             if "correlation_r" in t["headers"] and "source_hedges_g" in t["headers"]
             and "electrode_hedges_g" in t["headers"]
             and ("contrast" in t["headers"] or "hypothesis" in t["headers"])]
    if not cands:
        return None
    # Prefer the spectral band-power comparison over the aperiodic one.
    cands.sort(key=lambda t: ("aperiodic" in t["filename"].lower(), t["filename"]))
    return cands[0]

def _ci_sig(rec: dict, level: str) -> bool:
    """True if the ``{level}_hedges_g`` CI excludes zero (same-sign bounds)."""
    lo = _to_float(rec.get(f"{level}_ci_lo"))
    hi = _to_float(rec.get(f"{level}_ci_hi"))
    return lo is not None and hi is not None and lo != 0 and (lo > 0) == (hi > 0)

def _fcd_comparison_table(tables: list[dict]) -> dict | None:
    """The FCD source-vs-sensor comparison table (mean FCD + spatial CV)."""
    for t in tables:
        h = t["headers"]
        if ("corr_mean_r" in h and "source_mean_g" in h and "sensor_mean_g" in h
                and ("contrast" in h or "hypothesis" in h)):
            return t
    return None

def _roi_posthoc_table(tables: list[dict]) -> dict | None:
    """A per-ROI / per-channel posthoc table: a populated spatial unit column
    (``roi``/``spatial``) at ROI/channel scale (≈3–40 units, not a whole-brain
    vertex map), plus effect + significance + contrast. Used to name *which*
    ROIs differ, instead of the region-averaged global table that hides them."""
    best = None
    best_units = 0
    for t in tables:
        h = t["headers"]
        if "graph_metric" in h:   # nodal graph tables keep their own aggregation
            continue
        if not (("hypothesis" in h or "contrast" in h)
                and ("effect_size" in h or "hedges_g" in h) and "significant" in h):
            continue
        elem = _element_column(h)
        if elem not in ("roi", "spatial"):   # ROIs/channels only, not vertex maps
            continue
        recs = _records(h, t["rows"])
        units = {str(r.get(elem, "")).strip() for r in recs}
        units = {u for u in units if u.lower() not in _DEGENERATE}
        if not (3 <= len(units) <= 40):   # ROI/channel scale, not a vertex map
            continue
        # prefer the dedicated posthoc-per-unit table, else the most-detailed one
        score = (2 if "posthoc_roi" in t["filename"].lower() else
                 1 if "posthoc" in t["filename"].lower() else 0, len(units))
        if score > (2 if best and "posthoc_roi" in best["filename"].lower() else
                    1 if best and "posthoc" in best["filename"].lower() else 0, best_units):
            best, best_units = t, len(units)
    return best

def _roi_measure_label(rec: dict) -> str:
    """'Low Gamma relative' / 'exponent' — band + dv, collapsing the NA-band case."""
    band = str(rec.get("band") or "").strip()
    dv = str(rec.get("dv") or "").strip()
    if not band or band.lower() in _DEGENERATE:
        return dv or "value"
    return f"{band} {dv}" if dv and dv.lower() not in _DEGENERATE else band

# Canonical display for connectivity/coupling/method acronyms (matches the
# figure labels), so digests show 'AEC', 'dwPLI', … not 'aec', 'dwpli'.
_METRIC_DISPLAY = {
    "imag_coherence": "Imag. coherence", "coherence": "Coherence",
    "dwpli": "dwPLI", "wpli": "wPLI", "pli": "PLI", "dpli": "dPLI", "aec": "AEC",
    "partial_corr": "Partial corr.", "partial_correlation": "Partial corr.",
    "pac": "PAC", "aac": "AAC", "ppc": "PPC", "dtf": "DTF", "te": "TE",
    "inflow": "inflow", "outflow": "outflow", "netflow": "netflow",
}

def _pretty_metric(m) -> str:
    """Display form of a metric/measure token (AEC, dwPLI, …); pass others through."""
    if m is None:
        return ""
    return _METRIC_DISPLAY.get(str(m).strip().lower(), str(m))

# Band-name suffixes (lower/underscored) as they appear in connectivity figure
# filenames like ``circos_<metric>_<band>.png``. Multi-word bands are listed so
# ``low_gamma`` is matched before a bare ``gamma``.
_BAND_SUFFIXES = ("low_gamma", "high_gamma", "epsilon", "delta", "theta",
                  "alpha", "beta", "gamma")

def build_descriptive_matrix_summary(analysis, figure_names,
                                     contrast_labels=None) -> str | None:
    """Descriptive digest for a connectivity-*matrix* module that carries no
    inferential tables — e.g. ``roi_connectivity`` after its per-edge stats were
    retired (group inference moved to ``*_nbs`` / ``*_graph``). Names the metrics
    and bands the matrices span and points to the sibling modules that hold the
    inference, so the gallery entry isn't blank.

    ``figure_names`` are the module's figure filenames (``circos_*``/``heatmap_*``
    are parsed for ``<metric>``/``<band>``). Returns None if none parse (so it is
    a no-op for any module that isn't a connectivity-matrix module).
    """
    metrics: dict[str, str] = {}
    bands: set[str] = set()
    for fn in figure_names or ():
        stem = None
        for pre in ("circos_", "heatmap_"):
            if fn.startswith(pre):
                stem = fn[len(pre):].rsplit(".", 1)[0]
                break
        if stem is None:
            continue
        for band in _BAND_SUFFIXES:
            if stem.endswith("_" + band):
                metric = stem[: -(len(band) + 1)]
                if metric:
                    metrics[metric.lower()] = _pretty_metric(metric)
                    bands.add(band)
                break
    if not metrics:
        return None

    metric_list = ", ".join(sorted(metrics.values(), key=str.lower))
    n_metrics, n_bands = len(metrics), len(bands)
    n_contr = len(contrast_labels) if contrast_labels else 0

    prefix = analysis.rsplit("_", 1)[0]  # roi_connectivity -> roi
    siblings = (f"<strong>{escape(prefix)}_nbs</strong> (sub-networks) and "
                f"<strong>{escape(prefix)}_graph</strong> (graph metrics)")
    contr_txt = f" &times; {n_contr} group contrasts" if n_contr else ""
    lead = (f"Descriptive connectivity matrices — {n_metrics} "
            f"metric{'s' if n_metrics != 1 else ''} ({escape(metric_list)}) "
            f"across {n_bands} band{'s' if n_bands != 1 else ''}{contr_txt}.")
    note = f"Group-level inference for this family is reported in {siblings}."
    return ('<div class="sig-summary"><p class="sig-lead">' + lead + "</p>"
            '<p class="sig-note">' + note + "</p></div>")

def _graph_table(tables: list[dict]) -> dict | None:
    """A *global* graph-theory table: keyed by a ``graph_metric`` (global
    efficiency, modularity, …) with no populated spatial unit. Summarized by
    graph parameter, not by band, so the digest names *which* metrics differ.

    Per-ROI *nodal* graph tables (a real ``roi`` column: degree/clustering per
    node) are NOT matched — they keep the per-element aggregation.
    """
    for t in tables:
        h = t["headers"]
        if not ("graph_metric" in h and ("hypothesis" in h or "contrast" in h)
                and ("effect_size" in h or "hedges_g" in h)):
            continue
        elem = _element_column(h)
        if elem:
            recs = _records(h, t["rows"])
            if any(str(r.get(elem, "")).strip().lower() not in _DEGENERATE for r in recs):
                continue  # real per-element axis → not a graph-parameter summary
        return t
    return None

def _order_graph_bands(bands: set[str]) -> list[str]:
    known = [b for b in _GRAPH_BAND_ORDER if b in bands]
    return known + sorted(b for b in bands if b not in _GRAPH_BAND_ORDER)

def _cluster_table(tables: list[dict]):
    """Pick a vertex cluster-permutation table and the (p, direction) columns to
    read. The inferential unit for these modules is the *cluster* (with a
    corrected p), not the per-vertex row — so the digest must read one of these,
    never the truncated per-vertex ``*_stats.csv``.

    Two shapes, in preference order:
      A. ``cluster_results.csv`` — per-contrast difference clusters
         (contrast/band/metric/n_vertices/peak_t/p_corrected); this is what the
         cluster figures draw.
      B. the map-adapter ``*_hypotheses.csv`` — cluster rows carrying
         ``cluster_id``/``n_vertices``/``cluster_p``/``significant`` (used by the
         connectivity/directed/cross-freq/specparam vertex modules).
    Returns (table, p_col, direction_col) or (None, None, None).
    """
    for t in tables:
        h = t["headers"]
        if "p_corrected" in h and "n_vertices" in h and ("contrast" in h or "hypothesis" in h):
            return t, "p_corrected", ("peak_t" if "peak_t" in h else "cluster_stat")
    for t in tables:
        h = t["headers"]
        if (t["filename"].endswith("_hypotheses.csv") and "cluster_id" in h
                and "n_vertices" in h and "cluster_p" in h):
            return t, "cluster_p", ("peak_stat" if "peak_stat" in h else "mass")
    return None, None, None

def _cluster_measure_label(rec: dict) -> str:
    """Readable measure for a cluster row: band plus its dependent variable, e.g.
    'Low Gamma relative', 'spectral_slope', 'exponent'. Collapses the redundant
    case where the band *is* the measure (spectral_slope / peak_alpha maps)."""
    band = str(rec.get("band") or "").strip()
    meas = ""
    for col in ("metric", "dv", "parameter", "measure"):
        v = rec.get(col)
        if v not in (None, "") and str(v).strip().lower() not in _DEGENERATE:
            meas = str(v).strip()
            break
    if not band:
        return _pretty_metric(meas) or "map"
    if not meas or meas == band or meas.lower() in {"spectral_slope", "peak_alpha"}:
        return band
    return f"{band} {_pretty_metric(meas)}"

_DEGENERATE = {"", "na", "nan", "none"}

def _category_column(headers: list[str], records: list[dict]) -> str | None:
    """Per-contrast category axis: ``band``/``freq_pair`` for spectral tables,
    ``dv`` (exponent/offset) for aperiodic, ``parameter`` for specparam. Skips a
    column that is entirely NA (aperiodic carries a placeholder ``band = NA``)."""
    for col in ("band", "freq_pair", "dv", "parameter"):
        if col in headers:
            if any(
                v is not None and str(v).strip().lower() not in _DEGENERATE
                for v in (r.get(col) for r in records)
            ):
                return col
    for col in ("band", "freq_pair", "dv", "parameter"):
        if col in headers:
            return col
    return None


# --------------------------------------------------------------------------- #
# The study around a digest
# --------------------------------------------------------------------------- #
@dataclass
class Study:
    """What the study config says about its contrasts and groups."""

    labels: dict = field(default_factory=dict)        # contrast -> label
    tiers: dict = field(default_factory=dict)         # contrast -> tier / group label
    meta: dict = field(default_factory=dict)          # contrast -> {role, test, gate_on}
    order: list = field(default_factory=list)         # contrasts, in the config's order
    group_labels: dict = field(default_factory=dict)  # group id -> label
    design: dict = field(default_factory=dict)        # contrast -> {group_a, group_b}

    def label(self, contrast) -> str:
        return str(self.labels.get(contrast, contrast))

    def sorted(self, contrasts) -> list:
        """In the config's order; contrasts it does not list keep theirs, after."""
        rank = {c: i for i, c in enumerate(self.order)}
        return sorted(contrasts, key=lambda c: rank.get(c, len(rank)))

    def role(self, contrast) -> str | None:
        return (self.meta.get(contrast) or {}).get("role")

    def group(self, gid) -> str | None:
        return None if gid is None else str(self.group_labels.get(gid, gid))

    def key(self, contrast, rows, headers, effect_col) -> tuple[str | None, str]:
        """(test kind, the ``sig-groups`` span saying what ▲ means for it)."""
        design = self.design.get(contrast)
        kind = R.test_kind(rows, headers, effect_col, design)
        a, b = R.groups(rows, design)
        text = direction_text(kind, self.group(a), self.group(b))
        return kind, f' <span class="sig-groups">{text}</span>'


def _item(study: Study, contrast, body: str, null: bool = False, key: str = "") -> str:
    cls = ' class="sig-null-item"' if null else ""
    return (f'<li{cls}><span class="sig-contrast">{escape(study.label(contrast))}</span>'
            f'{key} {body}</li>')


def _null(text: str) -> str:
    return f'<span class="sig-none-inline">{text}</span>'


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def _lead(headline: str, counts: str, extra: str = "") -> str:
    return f'<p class="sig-lead">{headline}{counts}{extra}</p>'


def _headline(study: Study, best: dict, n_tests: int, noun: str = "effect",
              of: str = "test") -> str:
    """The confirmatory contrasts' results, or else the largest effect — named as
    the largest of how many tests, because it was selected for being largest.

    ``best`` maps a contrast to ``(magnitude, html, eligible)``: its most
    prominent result; ineligible ones (an omnibus or equivalence test) are not
    compared for "largest".
    """
    confirmatory = [c for c in study.sorted(best) if study.role(c) == "confirmatory"]
    if confirmatory:
        parts = [f'Confirmatory — <span class="sig-contrast-ref">{escape(study.label(c))}</span>: '
                 f'{best[c][1]}' for c in confirmatory]
        return '<span class="sig-top">' + "; ".join(parts) + ".</span> "
    pool = {c: v for c, v in best.items() if v[2]} or best
    if not pool:
        return ""
    c = max(study.sorted(pool), key=lambda k: pool[k][0])
    return (f'<span class="sig-top">Largest {noun} of {_plural(n_tests, of)} — '
            f'<span class="sig-contrast-ref">{escape(study.label(c))}</span>: '
            f'{pool[c][1]}.</span> ')


def _counts(n_sig: int, n_tests: int, noun: str, statement: str, k: int, n_contrasts: int,
            verb: str = "reach") -> str:
    verb = f"{verb} " if verb else ""
    return (f"{n_sig:,} of {_plural(n_tests, noun)} {verb}{statement}, "
            f"in {k} of {n_contrasts} comparisons.")


#: How a confidence-interval criterion reads in a count.
_CI_COUNT = ("have a 95% CI excluding 0 at source and/or sensor "
             "(multiple-comparison correction not recorded)")


# --------------------------------------------------------------------------- #
# One row, in words
# --------------------------------------------------------------------------- #
def _where(rec: dict, cat, facet_col=None, elem_col=None) -> str:
    """Where a result is: its category, facet and element (HTML)."""
    parts = []
    if cat and str(rec.get(cat) or "").strip().lower() not in _DEGENERATE:
        parts.append(f"<strong>{escape(_pretty_metric(rec.get(cat)))}</strong>")
    if facet_col and rec.get(facet_col):
        parts.append(f'<span class="sig-facet">{escape(_pretty_metric(rec[facet_col]))}</span>')
    if elem_col and str(rec.get(elem_col) or "").strip().lower() not in _DEGENERATE:
        parts.append(escape(str(rec.get(elem_col))))
    return " ".join(parts)


def _value(rec, headers, effect_col, ci=None) -> str:
    """``▲ g = 0.45`` for a signed effect, ``ω²p = 0.05`` / ``AUC = 0.81 (above
    chance)`` for an unsigned one."""
    v = _to_float(rec.get(effect_col))
    if v is None:
        return ""
    m = R.measure(rec, headers, effect_col)
    if R.signed(rec, headers, effect_col):
        return f'{arrow(v)} <span class="g">{effect_text(v, m, ci, signed_magnitude=True)}</span>'
    text = effect_text(v, m, ci)
    if effect_col == "auc":
        text += " (above chance)" if v > 0.5 else " (below chance)" if v < 0.5 else " (at chance)"
    return f'<span class="g">{text}</span>'


def _p(rec, corr) -> str:
    p = R.p_of(rec, corr)
    return f' <span class="sig-q">{p_text(p, corr["symbol"])}</span>' if p is not None else ""


def _magnitude(rec, effect_col) -> float:
    """How large an effect is: |value| for a signed measure, the value itself
    for an unsigned one (decoding, ω²)."""
    v = _to_float(rec.get(effect_col))
    if v is None:
        return 0.0
    unsigned = (effect_col in ("auc", "accuracy")
                or str(rec.get("effect_size_type") or "").strip() in R.UNSIGNED)
    return v if unsigned else abs(v)


def _largest(rows, effect_col):
    return max(rows, key=lambda r: _magnitude(r, effect_col)) if rows else None


def _equivalence_body(rows, headers, effect_col, corr, statement, where) -> str:
    """An equivalence contrast: the TOST outcome first; its difference tests'
    significant results after, as differences."""
    if "equivalent" in headers:
        flags = [str(r.get("equivalent") or "").strip().upper() for r in rows]
        n_eq = sum(f in ("TRUE", "T", "1", "YES") for f in flags)
        body = (f'<span class="sig-equiv">equivalent within the study margin in '
                f'{n_eq} of {_plural(len(rows), "test")}</span>')
    else:
        body = '<span class="sig-equiv">equivalence outcome not recorded</span>'
    diffs = [r for r in rows if _is_sig(r)]
    if diffs:
        best = _largest(diffs, effect_col)
        body += (f'; differs ({statement}) in {len(diffs)}: largest {where(best)} '
                 f'{_value(best, headers, effect_col)}{_p(best, corr)}')
    elif rows:
        best = _largest(rows, effect_col)
        body += (f'; no difference reaches {statement} — largest: {where(best)} '
                 f'{_value(best, headers, effect_col)}{_p(best, corr)}')
    return body


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build_significance_summary(tables: list[dict], contrast_labels: dict | None = None,
                               contrast_groups: dict | None = None,
                               contrast_meta: dict | None = None,
                               region_pair_table: dict | None = None,
                               contrast_order: list | None = None,
                               group_labels: dict | None = None,
                               contrast_design: dict | None = None) -> str | None:
    """Return a digest of every contrast's result, as HTML, or None.

    ``tables`` are embedded table dicts: ``{filename, headers, rows}``.
    ``contrast_labels`` maps raw contrast names to readable labels for display.
    ``contrast_groups`` maps contrast names to a tier/group label; when given, the
    digest is organized into sections in the group's first-seen (YAML) order.
    ``contrast_meta`` maps contrast names to ``{role, test, gate_on}``; each
    contrast is badged with its role, gated contrasts name their gate, and a
    confirmatory contrast leads the digest. ``contrast_order`` is the study's
    contrast order; ``group_labels`` name its groups; ``contrast_design`` maps a
    contrast to the two groups it compares when the tables do not say.
    """
    study = Study(labels=contrast_labels or {}, tiers=contrast_groups or {},
                  meta=contrast_meta or {},
                  order=list(contrast_order or (contrast_labels or {}).keys()),
                  group_labels=group_labels or {}, design=contrast_design or {})
    return build_digest(lambda t, _labels, _groups, **kw: _build_significance_summary(t, study, **kw),
                        tables, contrast_labels, contrast_groups, contrast_meta,
                        region_pair_table=region_pair_table)


def _build_significance_summary(tables, study: Study, region_pair_table=None):
    # Vertex cluster-permutation modules: the inferential unit is the cluster
    # (corrected p), so summarize the cluster table directly — otherwise the
    # digest would fall through to the truncated per-vertex table and miss most
    # significant clusters (and every contrast past the first).
    ctable, c_pcol, c_dcol = _cluster_table(tables)
    if ctable is not None:
        return _build_cluster_summary(ctable, c_pcol, c_dcol, study)

    # Graph-theory modules: summarize by graph parameter (which metrics differ),
    # not by the generic band axis — and don't let the empty ``spatial`` column
    # fool the per-element aggregation into a meaningless "1 ROI" count.
    gtable = _graph_table(tables)
    if gtable is not None:
        return _build_graph_summary(gtable, study)

    # Source-vs-sensor comparison (electrode_comparison): concordance + which
    # measures are significant at each level.
    cmptable = _comparison_table(tables)
    if cmptable is not None:
        return _build_comparison_summary(cmptable, study)

    fcdtable = _fcd_comparison_table(tables)
    if fcdtable is not None:
        return _build_fcd_comparison_summary(fcdtable, study)

    # Parcellated spectral modules (roi_psd/aperiodic, electrode_psd/aperiodic):
    # name the significant ROIs/channels from the per-unit posthoc table, rather
    # than the region-averaged global table that hides which units differ.
    rtable = _roi_posthoc_table(tables)
    if rtable is not None:
        return _build_roi_posthoc_summary(rtable, tables, study)

    table = _summary_table(tables)
    if table is None:
        # No effect-size table — fall back to an NBS sub-network digest if present.
        nbs = _nbs_table(tables)
        if nbs is not None:
            return _build_nbs_summary(nbs, study)
        return None
    return _build_effect_summary(table, tables, study, region_pair_table)


# --------------------------------------------------------------------------- #
# Effect tables (one row per test, or per element)
# --------------------------------------------------------------------------- #
def _build_effect_summary(table, tables, study: Study, region_pair_table):
    headers = table["headers"]
    records = _to_native(_records(headers, table["rows"]))
    cat = _category_column(headers, records)
    effect_col, _signed = _effect_column(headers)
    elem_col = _element_column(headers)
    facet_col, _ = _facet_column(headers, records)
    if facet_col == cat:  # don't repeat the category as its own facet (aperiodic dv)
        facet_col = None
    if elem_col:  # per-element tables aggregate over the facet too
        facet_col = None
    elif facet_col is None and "classifier" in headers:
        facet_col = "classifier"   # decoding: which classifier each result is
    corr = R.correction(headers, records)
    statement = correction_statement(corr["p_kind"], corr["method"], corr["symbol"])

    def where(rec):
        return _where(rec, cat, facet_col, elem_col)

    all_contrasts = study.sorted(_unique(records, "hypothesis"))
    by_contrast: dict[str, list[dict]] = {}
    for rec in records:
        if _to_float(rec.get(effect_col)) is not None:
            by_contrast.setdefault(rec.get("hypothesis"), []).append(rec)
    if not all_contrasts:
        return None

    # Protected post-hoc: for connectivity (a region-pair table is present), count
    # region pairs at uncorrected p<0.05 per (contrast, band, metric) — these are
    # the localized findings the circos show within an FDR-significant omnibus.
    rp_source = region_pair_table
    if rp_source is None:
        rp_source = next((t for t in tables
                          if "region_pair" in t["headers"] and "p_value" in t["headers"]), None)
    rp_counts: dict[tuple, int] = {}
    has_region_pairs = rp_source is not None and elem_col is None
    if has_region_pairs:
        for r in _to_native(_records(rp_source["headers"], rp_source["rows"])):
            p = _to_float(r.get("p_value"))
            if p is not None and p < 0.05:
                key = (r.get("hypothesis"), r.get("band"), r.get("metric"))
                rp_counts[key] = rp_counts.get(key, 0) + 1

    unit_s, unit_p = (("vertex", "vertices") if elem_col == "vertex_idx" else ("ROI", "ROIs"))
    item_by_contrast: dict[str, str] = {}
    best: dict[str, tuple] = {}
    n_tests = n_sig = 0
    sig_contrasts = 0
    n_equiv_tests = n_equivalent = 0
    for contrast in all_contrasts:
        rows = by_contrast.get(contrast, [])
        kind, key = study.key(contrast, rows, headers, effect_col)
        n_tests += len(rows)
        sig = [r for r in rows if _is_sig(r)]
        n_sig += len(sig)
        if sig:
            sig_contrasts += 1
        if not rows:
            item_by_contrast[contrast] = _item(study, contrast, _null("no effect recorded"),
                                               null=True, key=key)
            continue
        top = _largest(sig, effect_col) or _largest(rows, effect_col)
        top_html = (f"{where(top)} {_value(top, headers, effect_col)}{_p(top, corr)}"
                    + ("" if sig else " (n.s.)"))
        best[contrast] = (_magnitude(top, effect_col), top_html,
                          kind not in ("omnibus", "equivalence"))

        if kind == "equivalence":
            if "equivalent" in headers:
                n_equiv_tests += len(rows)
                n_equivalent += sum(str(r.get("equivalent") or "").strip().upper() in
                                    ("TRUE", "T", "1", "YES") for r in rows)
            body = _equivalence_body(rows, headers, effect_col, corr, statement, where)
            item_by_contrast[contrast] = _item(study, contrast, body, key=key)
        elif sig:
            if elem_col:
                chips = _aggregated_chips(sig, cat, headers, effect_col, corr, elem_col,
                                          unit_s, unit_p)
            else:
                chips = _per_record_chips(sig, cat, headers, effect_col, corr, facet_col,
                                          rp_counts if has_region_pairs else None)
            item_by_contrast[contrast] = _item(study, contrast, "".join(chips), key=key)
        else:
            largest = _largest(rows, effect_col)
            word = "best" if effect_col in ("auc", "accuracy") else "largest"
            item_by_contrast[contrast] = _item(
                study, contrast,
                _null(f"n.s. — {word}: {where(largest)} {_value(largest, headers, effect_col)}"
                      f"{_p(largest, corr)}; {_plural(len(rows), 'test')}"),
                null=True, key=key)

    body = _render_body(all_contrasts, item_by_contrast, study.tiers)
    extra = ""
    if n_equiv_tests:
        extra = (f" Equivalence (TOST, the study's margin) shown in {n_equivalent:,} of "
                 f"{_plural(n_equiv_tests, 'equivalence test')}.")
    if effect_col == "auc":
        extra += ' <span class="sig-key">chance AUC = 0.5</span>.'
    html = '<div class="sig-summary">'
    html += _lead(_headline(study, best, n_tests),
                  _counts(n_sig, n_tests, "test", statement, sig_contrasts, len(all_contrasts)),
                  extra)
    if has_region_pairs:
        html += (
            '<p class="sig-note">Region-pair counts are protected post-hocs '
            "(uncorrected p &lt; 0.05) within each significant omnibus; "
            "<em>diffuse</em> = no suprathreshold region pair. Each non-diffuse "
            "effect has a circos in the Figures tab.</p>"
        )
    html += body
    html += "</div>"
    return html


def _per_record_chips(rows, cat, headers, effect_col, corr, facet_col, rp_counts):
    """One chip per significant record (aggregated tables: vertex_graph, psd, …)."""
    chips = []
    for rec in sorted(rows, key=lambda r: -_magnitude(r, effect_col)):
        pairs = ""
        if rp_counts is not None:  # connectivity: annotate with gated region-pair detail
            k = (rec.get("hypothesis"), rec.get(cat), rec.get(facet_col) if facet_col else None)
            cnt = rp_counts.get(k, 0)
            pairs = (' <span class="sig-pairs">' + f"{cnt} region pair{'s' if cnt != 1 else ''}" + "</span>"
                     if cnt else ' <span class="sig-pairs diffuse">diffuse</span>')
        chips.append(
            f'<span class="sig-item">{_where(rec, cat, facet_col)} '
            f'{_value(rec, headers, effect_col)}{_p(rec, corr)}{pairs}</span>'
        )
    return chips


def _aggregated_chips(rows, cat, headers, effect_col, corr, elem_col, unit_s, unit_p):
    """One chip per (category) for per-element tables (roi_graph, specparam, …):
    collapse the elements to a count + the strongest effect, so a per-vertex/ROI
    table renders a handful of chips instead of thousands."""
    by_cat: dict[str, list[dict]] = {}
    for rec in rows:
        by_cat.setdefault(str(rec.get(cat, "")), []).append(rec)

    def _peak(recs):
        return max((_magnitude(r, effect_col) for r in recs), default=0.0)

    chips = []
    for cat_val, recs in sorted(by_cat.items(), key=lambda kv: -_peak(kv[1])):
        best = _largest(recs, effect_col)
        n_el = len({r.get(elem_col) for r in recs})
        chips.append(
            f'<span class="sig-item"><strong>{escape(_pretty_metric(cat_val))}</strong> '
            f'{_value(best, headers, effect_col)}{_p(best, corr)} '
            f'<span class="sig-pairs">{n_el} {unit_s if n_el == 1 else unit_p}</span></span>'
        )
    return chips


# --------------------------------------------------------------------------- #
# Source vs sensor
# --------------------------------------------------------------------------- #
def _ci(rec, level):
    lo, hi = _to_float(rec.get(f"{level}_ci_lo")), _to_float(rec.get(f"{level}_ci_hi"))
    return (lo, hi) if lo is not None and hi is not None else None


def _level_value(rec, level, effect) -> str:
    v = _to_float(rec.get(effect))
    if v is None:
        return "not recorded"
    return (f'{arrow(v)} <span class="g">{effect_text(v, "g", _ci(rec, level), signed_magnitude=True)}</span>'
            + ("" if _ci_sig(rec, level) else " (CI includes 0)"))


def _build_comparison_summary(table: dict, study: Study) -> str | None:
    """Digest the source-vs-sensor comparison: cross-subject concordance (r) plus,
    per contrast, each band/power measure's group effect at the source and the
    sensor level with its 95% CI — measures whose CI excludes 0 at either level
    first — and which level localizes it more sharply."""
    records = _to_native(_records(table["headers"], table["rows"]))
    headers = table["headers"]
    all_contrasts = study.sorted(_unique(records, "hypothesis"))

    rs_all = [_to_float(r.get("correlation_r")) for r in records]
    rs_all = [x for x in rs_all if x is not None]
    concord = ""
    if rs_all:
        concord = (' <span class="sig-key">source–sensor concordance r = '
                   f'{number(min(rs_all))}–{number(max(rs_all))} (median {number(sorted(rs_all)[len(rs_all)//2])})</span>.')

    def _measure(rec):
        band = str(rec.get("band") or "").strip()
        pt = str(rec.get("power_type") or rec.get("dv") or "").strip()
        return f"{band} {pt}".strip() if band else (pt or "value")

    def _sig(r):
        return _ci_sig(r, "source") or _ci_sig(r, "electrode")

    item_by_contrast: dict[str, str] = {}
    best: dict[str, tuple] = {}
    n_findings = sig_contrasts = 0
    for contrast in all_contrasts:
        rows = [r for r in records if r.get("hypothesis") == contrast]
        kind, key = study.key(contrast, rows, headers, "source_hedges_g")
        sig = [r for r in rows if _sig(r)]
        n_findings += len(sig)
        sig_contrasts += bool(sig)

        def _chip(rec):
            sg = _to_float(rec.get("source_hedges_g")) or 0.0
            eg = _to_float(rec.get("electrode_hedges_g")) or 0.0
            sharper = ' <span class="sig-facet">source localizes sharper</span>' if abs(sg) > abs(eg) else ""
            return (f'<span class="sig-item has-region"><strong>{escape(_measure(rec))}</strong> '
                    f'<span class="sig-region">source {_level_value(rec, "source", "source_hedges_g")} · '
                    f'sensor {_level_value(rec, "electrode", "electrode_hedges_g")}{sharper}</span></span>')

        top = (max(sig or rows, key=lambda r: abs(_to_float(r.get("source_hedges_g")) or 0.0))
               if rows else None)
        if top is not None:
            best[contrast] = (abs(_to_float(top.get("source_hedges_g")) or 0.0),
                              f'<strong>{escape(_measure(top))}</strong> source '
                              f'{_level_value(top, "source", "source_hedges_g")}', True)
        if sig:
            chips = [_chip(r) for r in sorted(sig, key=lambda r: -abs(_to_float(r.get("source_hedges_g")) or 0.0))]
            item_by_contrast[contrast] = _item(study, contrast, "".join(chips), key=key)
        elif top is not None:
            item_by_contrast[contrast] = _item(
                study, contrast,
                _null(f"no CI excludes 0 at either level — largest: {best[contrast][1]}"),
                null=True, key=key)
        else:
            item_by_contrast[contrast] = _item(study, contrast, _null("no effect recorded"),
                                               null=True, key=key)

    body = _render_body(all_contrasts, item_by_contrast, study.tiers)
    n_tests = len(records)
    html = '<div class="sig-summary">'
    html += _lead(_headline(study, best, n_tests),
                  _counts(n_findings, n_tests, "band/power measure", _CI_COUNT, sig_contrasts,
                          len(all_contrasts), verb=""),
                  concord)
    html += body
    html += "</div>"
    return html


def _build_fcd_comparison_summary(table: dict, study: Study) -> str | None:
    """Digest the FCD source-vs-sensor comparison: mean-FCD & spatial-CV
    concordance (r) plus, per contrast, the band × metric measures where the
    group effect's 95% CI excludes 0 at source and/or sensor, with the CIs."""
    records = _to_native(_records(table["headers"], table["rows"]))
    headers = table["headers"]
    all_contrasts = study.sorted(_unique(records, "hypothesis"))

    def _rng(col):
        xs = [_to_float(r.get(col)) for r in records]
        xs = [x for x in xs if x is not None]
        return f"{number(min(xs))}–{number(max(xs))}" if xs else None
    parts_r = []
    if _rng("corr_mean_r"):
        parts_r.append(f"mean-FCD r = {_rng('corr_mean_r')}")
    if _rng("corr_cv_r"):
        parts_r.append(f"spatial-CV r = {_rng('corr_cv_r')}")
    concord = f' <span class="sig-key">source–sensor concordance: {"; ".join(parts_r)}</span>.' if parts_r else ""

    def _measure(rec):
        return f"{str(rec.get('band') or '').strip()} {_pretty_metric(rec.get('metric'))}".strip()

    LEVELS = [("mean FCD", "source_mean", "sensor_mean"), ("spatial CV", "source_cv", "sensor_cv")]

    def _sig(r):
        return any(_ci_sig(r, s) or _ci_sig(r, e) for _, s, e in LEVELS)

    def _chip(rec):
        parts = []
        for lbl, src, sen in LEVELS:
            if _to_float(rec.get(f"{src}_g")) is None and _to_float(rec.get(f"{sen}_g")) is None:
                continue
            parts.append(f'{lbl}: source {_level_value(rec, src, f"{src}_g")}'
                         f' · sensor {_level_value(rec, sen, f"{sen}_g")}')
        return (f'<span class="sig-item has-region"><strong>{escape(_measure(rec))}</strong>'
                f'<span class="sig-region">{" ; ".join(parts)}</span></span>')

    item_by_contrast: dict[str, str] = {}
    best: dict[str, tuple] = {}
    n_findings = sig_contrasts = 0
    for contrast in all_contrasts:
        rows = [r for r in records if r.get("hypothesis") == contrast]
        _kind, key = study.key(contrast, rows, headers, "source_mean_g")
        sig = [r for r in rows if _sig(r)]
        n_findings += len(sig)
        sig_contrasts += bool(sig)
        top = (max(sig or rows, key=lambda r: abs(_to_float(r.get("source_mean_g")) or 0.0))
               if rows else None)
        if top is not None:
            best[contrast] = (abs(_to_float(top.get("source_mean_g")) or 0.0),
                              f'<strong>{escape(_measure(top))}</strong> mean FCD source '
                              f'{_level_value(top, "source_mean", "source_mean_g")}', True)
        if sig:
            chips = [_chip(r) for r in sorted(sig, key=lambda r: -abs(_to_float(r.get("source_mean_g")) or 0.0))]
            item_by_contrast[contrast] = _item(study, contrast, "".join(chips), key=key)
        elif top is not None:
            item_by_contrast[contrast] = _item(
                study, contrast, _null(f"no CI excludes 0 at either level — largest: {best[contrast][1]}"),
                null=True, key=key)
        else:
            item_by_contrast[contrast] = _item(study, contrast, _null("no effect recorded"),
                                               null=True, key=key)

    body = _render_body(all_contrasts, item_by_contrast, study.tiers)
    n_tests = len(records)
    html = '<div class="sig-summary">'
    html += _lead(_headline(study, best, n_tests),
                  _counts(n_findings, n_tests, "band/metric FCD measure", _CI_COUNT, sig_contrasts,
                          len(all_contrasts), verb=""),
                  concord)
    html += body
    html += "</div>"
    return html


# --------------------------------------------------------------------------- #
# Cluster permutation (vertices / channels)
# --------------------------------------------------------------------------- #
_PEAK_LABELS = {"peak_t": "peak t", "peak_stat": "peak statistic", "cluster_stat": "cluster statistic",
                "mass": "cluster mass"}


def _build_cluster_summary(table: dict, p_col: str, dir_col: str, study: Study) -> str | None:
    """Digest a vertex cluster-permutation table: every contrast's clusters
    (cluster-corrected p < 0.05), each with its band/measure, spatial extent (n
    vertices), direction and peak statistic, and p; a contrast without one shows
    its smallest-p cluster."""
    headers = table["headers"]
    records = _to_native(_records(headers, table["rows"]))
    has_flag = "significant" in headers
    rows_by: dict[str, list[dict]] = {}
    for rec in records:
        contrast = rec.get("hypothesis") or rec.get("contrast")
        if contrast:
            rows_by.setdefault(contrast, []).append(rec)
    all_contrasts = study.sorted(list(rows_by))
    if not all_contrasts:
        return None

    def _p(rec):
        return _to_float(rec.get(p_col))

    def _is_cluster_sig(rec):
        # cluster_results has no `significant` column → gate on the corrected p;
        # the map hypotheses table carries the adapter's own significance flag
        # (which also encodes equivalence for TOST rows).
        p = _p(rec)
        return _is_sig(rec) if has_flag else (p is not None and p < 0.05)

    # Sensor-montage modules (electrode_connectivity) reuse the vertex cluster
    # schema (``n_vertices``/``peak_vertex``), but the inferential unit is a
    # channel, not a source vertex — name it accordingly.
    fn = table["filename"].lower()
    unit_s, unit_p = (("channel", "channels")
                      if ("electrode" in fn or "channel" in fn)
                      else ("vertex", "vertices"))
    statement = correction_statement("corrected", "cluster-level")

    def _chip(rec, bare=False):
        d = _to_float(rec.get(dir_col))
        arrow_html = (arrow(d) + " ") if d is not None else ""
        n_vtx = _to_float(rec.get("n_vertices"))
        extent = (f'<span class="sig-pairs">{_plural(int(n_vtx), unit_s, unit_p)}</span>'
                  if n_vtx is not None else "")
        peak = (f' <span class="g">{_PEAK_LABELS.get(dir_col, escape(dir_col))} = {number(d)}</span>'
                if d is not None else "")
        p = _p(rec)
        pstr = f' <span class="sig-q">{p_text(p)}</span>' if p is not None else ""
        region = rec.get("region")
        region_html = (f'<span class="sig-region">{escape(str(region))}</span>'
                       if region not in (None, "") else "")
        cls = "sig-item has-region" if region_html else "sig-item"
        inner = (f'{arrow_html}<strong>{escape(_cluster_measure_label(rec))}</strong> '
                 f'{extent}{peak}{pstr}')
        return inner if bare else f'<span class="{cls}">{inner}{region_html}</span>'

    def _by_p(r):
        p = _p(r)
        return p if p is not None else 1.0

    item_by_contrast: dict[str, str] = {}
    best: dict[str, tuple] = {}
    n_findings = sig_contrasts = 0
    for contrast in all_contrasts:
        rows = rows_by[contrast]
        _kind, key = study.key(contrast, rows, headers, dir_col)
        sig = sorted((r for r in rows if _is_cluster_sig(r)), key=_by_p)
        n_findings += len(sig)
        sig_contrasts += bool(sig)
        top = sig[0] if sig else min(rows, key=_by_p)
        best[contrast] = (_to_float(top.get("n_vertices")) or 0.0,
                          _chip(top, bare=True) + ("" if sig else " (n.s.)"), bool(sig))
        if sig:
            chips = [_chip(r) for r in sig]
            # Region-bearing findings render one-per-row (block), so drop the space
            # separators that would otherwise leave stray gaps between block rows.
            joiner = "" if any("has-region" in c for c in chips) else " "
            item_by_contrast[contrast] = _item(study, contrast, joiner.join(chips), key=key)
        else:
            item_by_contrast[contrast] = _item(
                study, contrast,
                _null(f"no cluster reaches {statement} — "
                      + (f"smallest p: {_chip(top, bare=True)}" if _p(top) is not None
                         else f"no cluster p recorded: {_chip(top, bare=True)}")
                      + f"; {_plural(len(rows), 'cluster')}"),
                null=True, key=key)

    body = _render_body(all_contrasts, item_by_contrast, study.tiers)
    n_tests = len(records)
    html = '<div class="sig-summary">'
    html += _lead(_headline(study, best, n_tests, noun="cluster", of="cluster"),
                  _counts(n_findings, n_tests, "cluster", statement, sig_contrasts,
                          len(all_contrasts)))
    html += body
    html += "</div>"
    return html


# --------------------------------------------------------------------------- #
# Per-ROI / per-channel post hocs, with the whole-brain effect
# --------------------------------------------------------------------------- #
def _build_roi_posthoc_summary(table: dict, tables: list[dict], study: Study) -> str | None:
    """Digest parcellated spectral results at BOTH levels, per contrast × measure
    (band + dv): the whole-brain (region-averaged) effect AND the per-ROI/channel
    breakdown that names which units differ. Either level may be significant on
    its own (e.g. a global aperiodic effect with no surviving per-ROI unit). A
    contrast with neither shows its largest effect, and its p."""
    headers = table["headers"]
    records = _to_native(_records(headers, table["rows"]))
    elem = _element_column(headers)
    fn = table["filename"].lower()
    unit_word = "channel" if ("electrode" in fn or "channel" in fn) else "ROI"
    corr = R.correction(headers, records)
    statement = correction_statement(corr["p_kind"], corr["method"], corr["symbol"])

    # Every per-unit row, keyed (contrast, measure).
    roi_rows = [r for r in records
                if _to_float(r.get("effect_size")) is not None and r.get(elem)]
    gtbl = next((t for t in tables if "posthoc_global" in t["filename"].lower()), None)
    global_rows = []
    if gtbl is not None:
        global_rows = [r for r in _to_native(_records(gtbl["headers"], gtbl["rows"]))
                       if _to_float(r.get("effect_size")) is not None]
    all_contrasts = study.sorted(_unique(records, "hypothesis")
                                 + [c for c in _unique(global_rows, "hypothesis")
                                    if c not in _unique(records, "hypothesis")])
    if not all_contrasts:
        return None

    NAME_CAP = 8
    # The digest leads with the confirmatory contrast, else the largest single
    # effect (R5). Prefer the absolute DV: normalized DVs (relative/delta_ref) can
    # surface large redistribution artifacts that misrepresent the finding, while
    # absolute power is the honest primary read. Only when no absolute effect is
    # recorded does the lead fall back to the largest across all DVs.
    LEAD_DV = "absolute"

    def _unit_text(rec, unit):
        return (f'<strong>{escape(_roi_measure_label(rec))}</strong> {escape(unit)} '
                f'{_value(rec, headers, "effect_size")}{_p(rec, corr)}')

    item_by_contrast: dict[str, str] = {}
    best: dict[str, tuple] = {}
    best_pref: dict[str, tuple] = {}
    n_findings = 0
    sig_contrasts = 0
    for contrast in all_contrasts:
        c_rois = [r for r in roi_rows if r.get("hypothesis") == contrast]
        c_glob = [r for r in global_rows if r.get("hypothesis") == contrast]
        kind, key = study.key(contrast, c_rois or c_glob, headers, "effect_size")
        meas: dict[str, dict] = {}
        for r in c_rois:
            if _is_sig(r):
                meas.setdefault(_roi_measure_label(r), {"rois": [], "global": None})["rois"].append(r)
        for r in c_glob:
            if _is_sig(r):
                meas.setdefault(_roi_measure_label(r), {"rois": [], "global": None})["global"] = r

        # The contrast's most prominent result: its largest significant effect at
        # either level, else its largest effect (marked n.s.).
        cands = ([(m["global"], "whole-brain") for m in meas.values() if m["global"] is not None]
                 + [(r, str(r.get(elem))) for m in meas.values() for r in m["rois"]])
        is_sig = bool(cands)
        if not cands:
            cands = [(r, "whole-brain") for r in c_glob] + [(r, str(r.get(elem))) for r in c_rois]
        for rec, unit in cands:
            mag = _magnitude(rec, "effect_size")
            html = _unit_text(rec, unit) + ("" if is_sig else " (n.s.)")
            eligible = kind not in ("omnibus", "equivalence")
            if contrast not in best or mag > best[contrast][0]:
                best[contrast] = (mag, html, eligible)
            if (str(rec.get("dv") or "").strip().lower() == LEAD_DV
                    and (contrast not in best_pref or mag > best_pref[contrast][0])):
                best_pref[contrast] = (mag, html, eligible)

        if kind == "equivalence":
            rows = c_rois + c_glob
            item_by_contrast[contrast] = _item(
                study, contrast,
                _equivalence_body(rows, headers, "effect_size", corr, statement,
                                  lambda r: f'<strong>{escape(_roi_measure_label(r))}</strong> '
                                            f'{escape(str(r.get(elem) or "whole-brain"))}'),
                key=key)
            continue
        if not meas:
            if contrast in best:
                item_by_contrast[contrast] = _item(
                    study, contrast,
                    _null(f"n.s. — largest: {best[contrast][1].replace(' (n.s.)', '')}; "
                          f"{_plural(len(c_rois) + len(c_glob), 'test')}"),
                    null=True, key=key)
            else:
                item_by_contrast[contrast] = _item(study, contrast, _null("no effect recorded"),
                                                   null=True, key=key)
            continue
        sig_contrasts += 1

        def _peak(m):
            vals = [_magnitude(r, "effect_size") for r in m["rois"]]
            if m["global"] is not None:
                vals.append(_magnitude(m["global"], "effect_size"))
            return max(vals, default=0.0)

        chips = []
        for measure, m in sorted(meas.items(), key=lambda kv: -_peak(kv[1])):
            global_html = ""
            if m["global"] is not None:
                global_html = (f' <span class="sig-facet">whole-brain</span> '
                               f'{_value(m["global"], headers, "effect_size")}{_p(m["global"], corr)}')
                n_findings += 1
            rs = sorted(m["rois"], key=lambda x: -_magnitude(x, "effect_size"))
            count_html = region_html = ""
            if rs:
                named = []
                for r in rs[:NAME_CAP]:
                    named.append(f'{escape(str(r.get(elem)))}&nbsp;{_value(r, headers, "effect_size")}'
                                 f'{_p(r, corr)}')
                more = len(rs) - len(named)
                tail = f" (+{more} more)" if more > 0 else ""
                count_html = (f' <span class="sig-pairs">{len(rs)} {unit_word}'
                              f'{"s" if len(rs) != 1 else ""}</span>')
                region_html = f'<span class="sig-region">{", ".join(named)}{tail}</span>'
                n_findings += len(rs)
            # Every measure is its own block row — so a whole-brain-only contrast
            # (rescue/exploratory, no surviving per-ROI unit) lines up the same as
            # a per-ROI one instead of cramming onto a single line.
            chips.append(
                f'<span class="sig-item has-region"><strong>{escape(measure)}</strong>'
                f'{global_html}{count_html}{region_html}</span>')
        item_by_contrast[contrast] = _item(study, contrast, "".join(chips), key=key)

    body = _render_body(all_contrasts, item_by_contrast, study.tiers)
    n_tests = len(roi_rows) + len(global_rows)
    use_pref = any(v[2] for v in best_pref.values())
    lead_pool = best_pref if use_pref else best
    html = '<div class="sig-summary">'
    html += _lead(
        _headline(study, {**lead_pool, **{c: best[c] for c in best
                                           if study.role(c) == "confirmatory"}}, n_tests,
                  noun=f"{LEAD_DV}-power effect" if use_pref else "effect"),
        _counts(n_findings, n_tests, f"{unit_word}-level and whole-brain test", statement,
                sig_contrasts, len(all_contrasts)),
        f' <span class="sig-key">whole-brain effect + the {unit_word}s that differ</span>.')
    html += body
    html += "</div>"
    return html


# --------------------------------------------------------------------------- #
# Graph theory (by graph parameter)
# --------------------------------------------------------------------------- #
def _build_graph_summary(table: dict, study: Study) -> str | None:
    """Digest a graph-theory table by graph parameter: for each contrast, which
    graph metrics differ (global efficiency, modularity, …), in which bands and
    connectivity metrics, with the peak effect and direction. Answers 'which
    graph parameters are significant', not just which bands."""
    headers = table["headers"]
    records = _to_native(_records(headers, table["rows"]))
    all_contrasts = study.sorted(_unique(records, "hypothesis"))
    if not all_contrasts:
        return None
    corr = R.correction(headers, records)
    statement = correction_statement(corr["p_kind"], corr["method"], corr["symbol"])

    def _where_gm(rec):
        gm = rec.get("graph_metric") or ""
        label = _GRAPH_METRIC_LABEL.get(gm, str(gm).replace("_", " "))
        bits = [b for b in (rec.get("band"), _pretty_metric(rec.get("conn_metric"))) if b]
        return (f"<strong>{escape(label)}</strong>"
                + (f' <span class="sig-facet">{escape(", ".join(bits))}</span>' if bits else ""))

    item_by_contrast: dict[str, str] = {}
    best: dict[str, tuple] = {}
    n_findings = sig_contrasts = 0
    n_tests = 0
    for contrast in all_contrasts:
        rows = [r for r in records if r.get("hypothesis") == contrast
                and _to_float(r.get("effect_size")) is not None]
        kind, key = study.key(contrast, rows, headers, "effect_size")
        n_tests += len(rows)
        sig = [r for r in rows if _is_sig(r)]
        top = _largest(sig, "effect_size") or _largest(rows, "effect_size")
        if top is not None:
            best[contrast] = (_magnitude(top, "effect_size"),
                              f"{_where_gm(top)} {_value(top, headers, 'effect_size')}{_p(top, corr)}"
                              + ("" if sig else " (n.s.)"),
                              kind not in ("omnibus", "equivalence"))
        if kind == "equivalence" and rows:
            item_by_contrast[contrast] = _item(
                study, contrast,
                _equivalence_body(rows, headers, "effect_size", corr, statement, _where_gm), key=key)
            n_findings += len(sig)
            sig_contrasts += bool(sig)
            continue
        if not sig:
            body = (_null(f"n.s. — largest: {_where_gm(top)} {_value(top, headers, 'effect_size')}"
                          f"{_p(top, corr)}; {_plural(len(rows), 'test')}")
                    if top is not None else _null("no effect recorded"))
            item_by_contrast[contrast] = _item(study, contrast, body, null=True, key=key)
            continue
        sig_contrasts += 1
        by_gm: dict[str, list[dict]] = {}
        for r in sig:
            by_gm.setdefault(r.get("graph_metric") or "", []).append(r)
        chips = []
        for gm, rs in sorted(by_gm.items(), key=lambda kv: -max(_magnitude(x, "effect_size") for x in kv[1])):
            peak = _largest(rs, "effect_size")
            label = _GRAPH_METRIC_LABEL.get(gm, str(gm).replace("_", " "))
            bands = _order_graph_bands({str(x.get("band")) for x in rs if x.get("band")})
            conns = sorted({_pretty_metric(x.get("conn_metric")) for x in rs if x.get("conn_metric")})
            band_html = (f' <span class="sig-facet">{escape(", ".join(bands))}</span>'
                         if bands else "")
            conn_html = (f' <span class="sig-pairs">{escape(", ".join(conns))}</span>'
                         if conns else "")
            chips.append(
                f'<span class="sig-item"><strong>{escape(label)}</strong>'
                f'{band_html}{conn_html} largest {_value(peak, headers, "effect_size")}'
                f'{_p(peak, corr)}</span>')
            n_findings += len(rs)
        item_by_contrast[contrast] = _item(study, contrast, "".join(chips), key=key)

    body = _render_body(all_contrasts, item_by_contrast, study.tiers)
    html = '<div class="sig-summary">'
    html += _lead(_headline(study, best, n_tests),
                  _counts(n_findings, n_tests, "graph-metric test", statement, sig_contrasts,
                          len(all_contrasts)),
                  ' <span class="sig-key">grouped by graph parameter; bands and connectivity '
                  'metric listed</span>.')
    html += body
    html += "</div>"
    return html


# --------------------------------------------------------------------------- #
# Network-Based Statistic
# --------------------------------------------------------------------------- #
def _build_nbs_summary(table: dict, study: Study) -> str | None:
    """Digest an NBS component table: every contrast's sub-networks per (band,
    metric), parsed from the ``key`` column (``<contrast>_<band>[_<metric>]``),
    significant ones (component-level family-wise p < 0.05) listed, the largest
    component shown for a contrast without one."""
    records = _records(table["headers"], table["rows"])
    comps_by: dict[str, list[tuple]] = {}
    for rec in records:
        contrast, band, metric = _parse_nbs_key(str(rec.get("key", "")))
        if contrast is None:
            continue
        comps_by.setdefault(contrast, []).append(
            (band, metric, _to_float(rec.get("n_edges")), _to_float(rec.get("p_corrected")),
             rec.get("region"), rec.get("direction"),
             _to_float(rec.get("n_edges_increase")), _to_float(rec.get("n_edges_decrease"))))
    all_contrasts = study.sorted(list(comps_by))
    if not all_contrasts:
        return None
    statement = correction_statement("fwe", "NBS")

    def _chip(comp, bare=False):
        band, metric, n_edges, p, region, direction, n_inc, n_dec = comp
        facet = (f' <span class="sig-facet">{escape(_pretty_metric(metric))}</span>'
                 if metric else "")
        edges = f"{int(n_edges)}-edge " if n_edges is not None else ""
        # Direction: NBS thresholds |t|, so a sub-network can be up-, down-, or
        # mixed-regulation. ▲ = group A > B, ▼ = group A < B.
        dstr = str(direction or "").strip().lower()
        if dstr == "increase":
            arrow_html = '<span class="arrow up">&#9650;</span> '
        elif dstr == "decrease":
            arrow_html = '<span class="arrow down">&#9660;</span> '
        elif dstr == "mixed" and n_inc is not None and n_dec is not None:
            arrow_html = (f'<span class="sig-mixed">&#9650;{int(n_inc)}/'
                          f'&#9660;{int(n_dec)}</span> ')
        else:
            arrow_html = ""
        region_html = (f'<span class="sig-region">{escape(str(region))}</span>'
                       if region not in (None, "") else "")
        cls = "sig-item has-region" if region_html else "sig-item"
        band_html = f"<strong>{escape(band)}</strong>" if band else ""
        pstr = f" ({p_text(p)})" if p is not None else ""
        inner = f'{arrow_html}{band_html}{facet} <span class="sig-pairs">{edges}sub-network{pstr}</span>'
        return inner if bare else f'<span class="{cls}">{inner}{region_html}</span>'

    def _is_comp_sig(comp):
        return comp[3] is not None and comp[3] < 0.05

    item_by_contrast: dict[str, str] = {}
    best: dict[str, tuple] = {}
    n_findings = sig_contrasts = 0
    for contrast in all_contrasts:
        comps = comps_by[contrast]
        design = study.design.get(contrast)
        a, b = R.groups([], design)
        kind = "two_group" if a else None
        key = (f' <span class="sig-groups">'
               f'{direction_text(kind, study.group(a), study.group(b))}</span>')
        sig = sorted((c for c in comps if _is_comp_sig(c)), key=lambda c: c[3])
        n_findings += len(sig)
        sig_contrasts += bool(sig)
        top = (max(sig, key=lambda c: c[2] or 0.0) if sig
               else max(comps, key=lambda c: c[2] or 0.0))
        best[contrast] = (top[2] or 0.0, _chip(top, bare=True) + ("" if sig else " (n.s.)"), bool(sig))
        if sig:
            chips = [_chip(c) for c in sig]
            joiner = "" if any("has-region" in c for c in chips) else " "
            item_by_contrast[contrast] = _item(study, contrast, joiner.join(chips), key=key)
        else:
            item_by_contrast[contrast] = _item(
                study, contrast,
                _null(f"no sub-network reaches {statement} — largest: {_chip(top, bare=True)}; "
                      f"{_plural(len(comps), 'component')}"),
                null=True, key=key)

    body = _render_body(all_contrasts, item_by_contrast, study.tiers)
    n_tests = len(records)
    html = '<div class="sig-summary">'
    html += _lead(_headline(study, best, n_tests, noun="sub-network", of="component"),
                  _counts(n_findings, n_tests, "component", statement, sig_contrasts,
                          len(all_contrasts)))
    html += body
    html += "</div>"
    return html
