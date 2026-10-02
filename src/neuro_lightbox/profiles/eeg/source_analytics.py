"""What the EEG profile knows about source-analytics' output.

The analysis metadata (domain / supplements, read from source-analytics' own
interpreter), the part of its ``provenance.json`` the gallery shows, and the
analyses it retired or aliased, which an older results tree still carries.
"""

from __future__ import annotations

import json

#: Analyses that left source-analytics in v0.8.0, for the unmaintained
#: source-analytics-vertex plugin. A vertex map describes one arbitrary source
#: placement; the ROI analyses over Monte Carlo operators replaced them.
#:
#: Filtered out of every gallery, rather than merely absent, because an old
#: results tree still carries their tables and figures and would otherwise keep
#: publishing them next to current results with nothing to mark them as retired.
#: Separate from `exclude_analyses`, which a study overrides freely — overriding
#: that should not quietly bring these back. `include_retired` is the opt-in.
RETIRED_ANALYSES: frozenset = frozenset({
    "vertex_cluster", "vertex_connectivity", "vertex_cross_freq", "vertex_directed",
    "vertex_evoked", "vertex_graph", "vertex_nbs", "vertex_network",
    "vertex_signature", "vertex_spatial", "vertex_specparam", "fcd_comparison",
    # old spellings, so a frozen study config does not slip one through
    "wholebrain", "spatial_lmm", "specparam_vertex", "mvpa", "vertex_mvpa",
})

#: Omitted by default: the combined network aliases, superseded by the split
#: graph + nbs modules. A study can override via `exclude_analyses:`.
DEFAULT_EXCLUDE = ("roi_network", "vertex_network")


def filter_retired(scan, include_retired: bool, log) -> None:
    """Drop the retired analyses from the scan (in place) unless asked not to.

    Dropped first and separately from ``exclude_analyses``, so that a study
    overriding that cannot bring them back by accident.
    """
    if include_retired:
        return

    def _retired(e):
        return (e.analysis in RETIRED_ANALYSES
                or getattr(e, "paradigm", None) in RETIRED_ANALYSES)
    found = sorted({e.analysis for e in (*scan.figures, *scan.tables) if _retired(e)})
    if found:
        scan.figures = [e for e in scan.figures if not _retired(e)]
        scan.tables = [e for e in scan.tables if not _retired(e)]
        log(f"  Skipped retired analyses: {', '.join(found)} — these left "
            f"source-analytics in v0.8.0 for the unmaintained "
            f"source-analytics-vertex plugin. Pass --include-retired to "
            f"publish them anyway.")


def read_analysis_meta(python: str | None, log=lambda *a, **k: None) -> dict:
    """Read source-analytics' ANALYSIS_METADATA (domain / supplements / …).

    The gallery groups analyses by ``domain`` and nests each secondary under the
    primary it ``supplements``. The single source of truth lives in
    source-analytics, so we read it from that interpreter (same subprocess
    pattern as the brain-mosaic / circos workers). Without that interpreter the
    copy bundled here (source-analytics v0.8.2's, ``analysis_meta.json``) is
    used, and the build says so: grouping should not depend on which machine
    builds the gallery.
    """
    import subprocess

    # Fall back to the default source-analytics venv (same as circos / mosaics)
    # when the study didn't pin paths.source_analytics_python.
    from .circos import _resolve as _resolve_sa_python

    py = _resolve_sa_python(python)
    if not py.exists():
        log(f"  Analysis metadata: no source-analytics interpreter at {py}; using the "
            f"bundled copy (source-analytics {BUNDLED_META_VERSION})")
        return bundled_analysis_meta()

    code = (
        "import json; from source_analytics.core import analysis_meta; "
        "print(json.dumps(analysis_meta()))"
    )
    try:
        out = subprocess.run(
            [str(py), "-c", code], capture_output=True, text=True, timeout=60
        )
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout.strip().splitlines()[-1])
        log("  WARNING: source-analytics' analysis metadata unavailable (import failed: "
            f"{out.stderr.strip()[-300:]}); using the bundled copy "
            f"(source-analytics {BUNDLED_META_VERSION})")
    except Exception as exc:  # noqa: BLE001
        log(f"  WARNING: source-analytics' analysis metadata unavailable ({exc}); using the "
            f"bundled copy (source-analytics {BUNDLED_META_VERSION})")
    return bundled_analysis_meta()


#: The source-analytics release whose ``analysis_meta()`` is bundled.
BUNDLED_META_VERSION = "v0.8.2"


def bundled_analysis_meta() -> dict:
    """source-analytics' analysis metadata as of BUNDLED_META_VERSION."""
    from pathlib import Path

    return json.loads((Path(__file__).parent / "analysis_meta.json").read_text())


def trim_provenance(record: dict) -> dict:
    """The parts of source-analytics' provenance.json the gallery shows.

    The file also carries the full subject-id list and the lifecycle steps, which
    are provenance rather than something a reader of a figure acts on. Keeping
    the manifest to what is displayed matters because it is inlined into
    index.html, once per analysis.
    """
    loc = record.get("localization") or {}
    plugins = {name: info for name, info in (record.get("plugins") or {}).items()
               if isinstance(info, dict) and info.get("provides_this_analysis")}
    out = {
        "written": record.get("written"),
        "source_analytics": (record.get("source_analytics") or {}).get("version"),
        "n_subjects": (record.get("subjects") or {}).get("n"),
        "groups": (record.get("subjects") or {}).get("groups") or {},
        "localization": {
            "description": loc.get("description"),
            "version": loc.get("version"),
            "atlas": loc.get("atlas"),
            "source_sampling": loc.get("source_sampling"),
            "inverse_method": loc.get("inverse_method"),
            "n_unrecorded": loc.get("n_unrecorded") or 0,
        },
    }
    if plugins:
        out["plugin"] = ", ".join(
            f"{name} {info.get('version') or '?'}" for name, info in sorted(plugins.items()))
    caveats = record.get("parcel_caveats") or {}
    if caveats:
        out["parcel_caveats"] = caveats
    return out
