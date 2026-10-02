"""Build the manifest.json from scan results."""

from __future__ import annotations

import csv
from pathlib import Path

from .scanner import ScanResult


def _read_csv(path: Path) -> dict:
    """Read a CSV file and return {headers: [...], rows: [[...], ...]}."""
    rows = []
    headers = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i == 0:
                headers = row
            else:
                rows.append(row)
    return {"headers": headers, "rows": rows}


def build_manifest(scan: ScanResult, title: str, max_table_rows: int = 500,
                   contrast_labels: dict | None = None,
                   contrast_groups: dict | None = None,
                   contrast_meta: dict | None = None,
                   analysis_meta: dict | None = None,
                   paradigm_display: dict | None = None,
                   group_labels: dict | None = None,
                   group_order: list | None = None,
                   profile=None) -> dict:
    """Build the manifest dictionary from aggregated scan results.

    Tables are embedded as parsed CSV data (row-capped; the full CSV is copied
    to ``tables/`` and linked) and summaries as generated HTML digests, so the
    gallery works without a server (no fetch() needed).

    ``group_labels`` / ``group_order`` (from the study YAML) drive how treatment
    groups are named and ordered in the UI.

    ``analysis_meta`` (from the profile) attaches a ``meta`` block — ``domain``
    and ``supplements`` — to each analysis so the gallery can group by domain
    and nest each secondary under the primary it supplements.

    ``contrast_meta`` (read from the study YAML) carries each contrast's
    hypothesis-testing metadata — ``role``, ``test``, ``gate_on`` — keyed by
    contrast name. The digest badges each contrast with its role
    (confirmatory / exploratory) and notes what a gated contrast depends on.

    ``profile`` (default: the default profile) writes the digests, trims each
    analysis's provenance, and fills its inputs block.
    """
    from .profiles import get_profile

    profile = profile or get_profile()
    analysis_meta = analysis_meta or {}
    manifest = {
        "title": title,
        "paradigms": {},
        # Per-paradigm nav display: paradigm key -> {group, label}. Empty = flat nav.
        "paradigm_meta": paradigm_display or {},
        # Per-contrast hypothesis metadata: name -> {role, test, gate_on}.
        "contrast_meta": contrast_meta or {},
        # Per-contrast readable labels: name -> label. Also serves as the
        # contrast vocabulary the frontend uses to group figures by contrast.
        "contrast_labels": contrast_labels or {},
        # Treatment-group display names + order (study YAML groups: / group_order:).
        "group_labels": group_labels or {},
        "group_order": list(group_order or []),
    }
    # The profile's inputs side (subjects / QC of what the analyses ran on).
    if profile.inputs_key:
        manifest[profile.inputs_key] = {}
    manifest["sources"] = []

    # Collect unique source labels
    source_labels = set()
    for fig in scan.figures:
        source_labels.add(fig.source_label)
    for tbl in scan.tables:
        source_labels.add(tbl.source_label)
    manifest["sources"] = sorted(source_labels)

    # Group analytics figures by paradigm > analysis > source
    for fig in scan.figures:
        if fig.category != "analytics":
            continue
        paradigm = fig.paradigm
        analysis = fig.analysis
        source = fig.source_label

        if paradigm not in manifest["paradigms"]:
            manifest["paradigms"][paradigm] = {}
        if analysis not in manifest["paradigms"][paradigm]:
            manifest["paradigms"][paradigm][analysis] = {
                "figures": {},
                "tables": {},
                "summary": None,
            }

        entry = manifest["paradigms"][paradigm][analysis]
        if source not in entry["figures"]:
            entry["figures"][source] = []
        entry["figures"][source].append(
            {
                "path": f"figures/{fig.gallery_rel_path}",
                "thumb": f"figures/{fig.thumb_rel_path}",
                "filename": fig.filename,
            }
        )

    # Group tables by paradigm > analysis > source — embed CSV data inline
    for tbl in scan.tables:
        paradigm = tbl.paradigm
        analysis = tbl.analysis
        source = tbl.source_label

        if paradigm not in manifest["paradigms"]:
            manifest["paradigms"][paradigm] = {}
        if analysis not in manifest["paradigms"][paradigm]:
            manifest["paradigms"][paradigm][analysis] = {
                "figures": {},
                "tables": {},
                "summary": None,
            }

        entry = manifest["paradigms"][paradigm][analysis]
        if source not in entry["tables"]:
            entry["tables"][source] = []

        table_data = _read_csv(tbl.src_path)
        total_rows = len(table_data["rows"])
        truncated = total_rows > max_table_rows
        tbl_entry = {
            "filename": tbl.filename,
            "csv": tbl.gallery_rel_path,
            "headers": table_data["headers"],
            "rows": table_data["rows"][:max_table_rows] if truncated else table_data["rows"],
        }
        if truncated:
            tbl_entry["truncated"] = True
            tbl_entry["total_rows"] = total_rows
        entry["tables"][source].append(tbl_entry)

    # Summaries — a concise 'significant results by contrast' digest derived from
    # each module's tables by the profile, NOT a verbose report verbatim.
    #
    # The digest must run on FULL tables, not the row-capped copies embedded for
    # display — otherwise a large per-unit posthoc table (ordered by contrast) is
    # truncated and only the first contrast's units survive.
    full_tables_by_module: dict[tuple, list[dict]] = {}
    for tbl in scan.tables:
        try:
            data = _read_csv(tbl.src_path)
        except Exception:  # noqa: BLE001
            continue
        full_tables_by_module.setdefault((tbl.paradigm, tbl.analysis), []).append(
            {"filename": tbl.filename, "headers": data["headers"], "rows": data["rows"]})

    n_summaries = 0
    for paradigm, analyses in manifest["paradigms"].items():
        for analysis, entry in analyses.items():
            module_tables = full_tables_by_module.get((paradigm, analysis))
            full = bool(module_tables)
            if not module_tables:  # fall back to embedded copies if a read failed
                module_tables = [t for src in entry["tables"].values() for t in src]
            summary_html = profile.digest(module_tables, full, contrast_labels,
                                          contrast_groups, contrast_meta)
            # A module with no inferential tables gets the profile's descriptive
            # digest, built from its figure filenames, if it has one.
            if summary_html is None:
                fig_names = [f["filename"]
                             for src in entry["figures"].values() for f in src]
                summary_html = profile.descriptive_digest(
                    analysis, fig_names, contrast_labels)
            entry["summary"] = summary_html
            if summary_html:
                n_summaries += 1

            # Domain / supplements metadata (for domain-grouped nav + nesting).
            m = analysis_meta.get(analysis, {})
            entry["meta"] = {
                "domain": m.get("domain", "Other"),
                "supplements": m.get("supplements"),
                "description": m.get("description"),
                "about": m.get("about"),
                "display_name": m.get("display_name"),
            }

            # What produced these tables (the provenance.json beside them),
            # trimmed by the profile to what a reader acts on. Absent for an
            # older run, which the gallery shows as unrecorded rather than
            # inventing.
            record = (getattr(scan, "provenance", None) or {}).get((paradigm, analysis))
            if record:
                entry["provenance"] = profile.trim_provenance(record)

    if profile.inputs_key:
        profile.add_inputs(manifest[profile.inputs_key], scan)

    # Compute stats
    manifest["stats"] = {
        "total_figures": len(scan.figures),
        "total_tables": len(scan.tables),
        "total_summaries": n_summaries,
        "paradigm_count": len(manifest["paradigms"]),
    }

    return manifest
