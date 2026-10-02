"""The EEG profile's inputs side: source-localization pipelines and their QC.

Each localization input (``paths.localizations``) is a source-localization output
tree: per-subject pipeline figures under ``derivatives/sub-*/pipeline/figures``,
the resolved config each run left beside its data, and a ``qc/`` folder with
figures, a metrics CSV and a report. They make the gallery's Localization
section (manifest key ``localization``): subjects, QC, and what built each
pipeline.
"""

from __future__ import annotations

from pathlib import Path

from ...scanner import FigureEntry, QCEntry, ScanResult, _slugify, qc_csv_to_json
from .qc_meta import compute_subject_meta

#: The FigureEntry category, gallery folder and manifest key of this inputs side.
CATEGORY = "localization"


#: Settings that decide the numbers. Two subjects that differ on any of them
#: were not measured the same way. Mirrors source-analytics' RunManifest.
_RUN_FIELDS = ("atlas", "bem", "source_space", "sampling", "inverse", "orientation")


def _read_run(data_dir: Path) -> dict | None:
    """The resolved config source-localization 0.4.2+ leaves beside its outputs.

    Returns None when absent — a run from before that, whose outputs cannot say
    what built them. The gallery shows "not recorded" rather than guessing.
    """
    path = data_dir / "config_resolved.yaml"
    if not path.exists():
        return None
    try:
        import yaml

        with open(path) as f:
            snapshot = yaml.safe_load(f) or {}
    except Exception:
        return None

    cfg = snapshot.get("config") or {}
    src = cfg.get("source_space") or {}
    surface = src.get("surface") or {}
    inverse = cfg.get("inverse") or {}
    pipeline = cfg.get("pipeline") or {}
    method = surface.get("method")
    return {
        "version": snapshot.get("source_localization_version"),
        "preset": (cfg.get("provenance") or {}).get("preset"),
        "atlas": (cfg.get("provenance") or {}).get("atlas"),
        "bem": pipeline.get("bem_type"),
        "source_space": (pipeline.get("source_type") or "")
                        + (f"/{method}" if method else ""),
        "sampling": src.get("source_sampling") or "fixed",
        "inverse": inverse.get("method"),
        "orientation": inverse.get("orientation"),
    }


def _summarise_runs(per_subject: dict) -> dict | None:
    """Collapse per-subject run info to one description for the source.

    ``mismatched`` lists the settings the subjects disagree on. A gallery that
    silently showed the first subject's settings for a mixed cohort would be
    describing a study that was not run.
    """
    known = {k: v for k, v in per_subject.items() if v}
    if not known:
        return None
    first = next(iter(known.values()))
    mismatched = sorted(
        field for field in _RUN_FIELDS
        if len({v.get(field) for v in known.values()}) > 1
    )
    return {
        **first,
        "n_subjects": len(known),
        "n_unrecorded": len(per_subject) - len(known),
        "mismatched": mismatched,
    }


class LocalizationScanner:
    """Scan a source-localization output directory."""

    def __init__(self, path: Path, label: str):
        self.path = Path(path)
        self.label = label

    def scan(self) -> ScanResult:
        result = ScanResult()
        per_subject: dict = {}

        # Per-subject pipeline figures
        deriv = self.path / "derivatives"
        if deriv.exists():
            for sub_dir in sorted(deriv.iterdir()):
                if not sub_dir.is_dir() or not sub_dir.name.startswith("sub-"):
                    continue
                sub_id = sub_dir.name
                per_subject[sub_id] = _read_run(sub_dir / "pipeline" / "data")
                fig_dir = sub_dir / "pipeline" / "figures"
                if fig_dir.exists():
                    for fig in sorted(fig_dir.glob("*.png")):
                        result.figures.append(
                            FigureEntry(
                                src_path=fig,
                                category=CATEGORY,
                                source_label=self.label,
                                subject=sub_id,
                                filename=fig.name,
                            )
                        )

        # QC figures
        qc_dir = self.path / "qc"
        if qc_dir.exists():
            qc_figs = qc_dir / "figures"
            if qc_figs.exists():
                for fig in sorted(qc_figs.glob("*.png")):
                    result.figures.append(
                        FigureEntry(
                            src_path=fig,
                            category=CATEGORY,
                            source_label=self.label,
                            filename=fig.name,
                        )
                    )

            # QC metrics and report
            qc_entry = QCEntry(source_label=self.label)
            metrics = qc_dir / "qc_metrics.csv"
            if metrics.exists():
                qc_entry.metrics_path = metrics
            report = qc_dir / "qc_report.html"
            if report.exists():
                qc_entry.report_path = report
            if qc_entry.metrics_path or qc_entry.report_path:
                result.qc_entries.append(qc_entry)

        run = _summarise_runs(per_subject)
        if run is not None:
            result.runs[self.label] = run

        return result


def add_inputs(block: dict, scan: ScanResult) -> None:
    """Fill the manifest's ``localization`` block: subjects and QC per pipeline,
    and what built it."""
    # Localization entries grouped by source
    for fig in scan.figures:
        if fig.category != CATEGORY:
            continue
        source = fig.source_label
        if source not in block:
            block[source] = {"subjects": {}, "qc_figures": []}

        entry = block[source]
        if fig.subject:
            if fig.subject not in entry["subjects"]:
                entry["subjects"][fig.subject] = []
            entry["subjects"][fig.subject].append(
                {
                    "path": f"figures/{fig.gallery_rel_path}",
                    "thumb": f"figures/{fig.thumb_rel_path}",
                    "filename": fig.filename,
                }
            )
        else:
            entry["qc_figures"].append(
                {
                    "path": f"figures/{fig.gallery_rel_path}",
                    "thumb": f"figures/{fig.thumb_rel_path}",
                    "filename": fig.filename,
                }
            )

    # QC entries — embed metrics inline + per-subject group/outlier metadata
    for qc in scan.qc_entries:
        source = qc.source_label
        if source not in block:
            block[source] = {"subjects": {}, "qc_figures": []}
        if qc.metrics_path:
            metrics = qc_csv_to_json(qc.metrics_path)
            block[source]["qc_metrics"] = metrics
            subject_keys = list(block[source].get("subjects", {}).keys())
            meta = compute_subject_meta(metrics, subject_keys)
            block[source]["subject_meta"] = meta
            block[source]["n_outliers"] = sum(1 for m in meta.values() if m["outliers"])
        if qc.report_path:
            block[source]["qc_report"] = f"qc/{_slugify(source)}/qc_report.html"

    # What source-localization run built each pipeline. The gallery shows the
    # atlas, geometry, inverse and sampling mode, because two galleries that
    # look identical can be reporting different measurements.
    for source, run in (getattr(scan, "runs", None) or {}).items():
        if source not in block:
            block[source] = {"subjects": {}, "qc_figures": []}
        block[source]["run"] = run
