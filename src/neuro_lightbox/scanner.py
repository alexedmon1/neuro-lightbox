"""Scan input directories for figures, tables, and QC artefacts."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FigureEntry:
    """A discovered figure file."""

    src_path: Path
    category: str  # "analytics", or the inputs category a profile names
    source_label: str
    paradigm: str = ""
    analysis: str = ""
    subject: str = ""
    filename: str = ""

    @property
    def gallery_rel_path(self) -> str:
        """Relative path within the gallery figures/ directory."""
        label_slug = _slugify(self.source_label)
        if self.category == "analytics":
            return f"analytics/{label_slug}/{self.paradigm}/{self.analysis}/{self.filename}"
        elif self.subject:
            return f"{self.category}/{label_slug}/subjects/{self.subject}/{self.filename}"
        else:
            return f"{self.category}/{label_slug}/qc/{self.filename}"

    @property
    def thumb_rel_path(self) -> str:
        """Relative path for the thumbnail (always a JPEG)."""
        base = self.gallery_rel_path
        return "thumbs/" + re.sub(r"\.(png|jpe?g|webp)$", ".jpg", base, flags=re.IGNORECASE)


@dataclass
class TableEntry:
    """A discovered CSV table."""

    src_path: Path
    source_label: str
    paradigm: str
    analysis: str
    filename: str
    #: The column dictionary beside a specification table (``<table>.json``), copied with it.
    dictionary: Path | None = None

    @property
    def gallery_rel_path(self) -> str:
        return f"tables/{self.paradigm}/{self.analysis}/{self.filename}"


@dataclass
class QCEntry:
    """QC metrics and report."""

    metrics_path: Path | None = None
    report_path: Path | None = None
    source_label: str = ""


@dataclass
class ScanResult:
    """Aggregated scan results from all scanners."""

    figures: list[FigureEntry] = field(default_factory=list)
    tables: list[TableEntry] = field(default_factory=list)
    qc_entries: list[QCEntry] = field(default_factory=list)
    #: input source_label -> what built that input (the profile's own record).
    runs: dict = field(default_factory=dict)
    #: (paradigm, analysis) -> the provenance.json beside those tables.
    provenance: dict = field(default_factory=dict)
    #: (paradigm, analysis) -> its :class:`~neuro_lightbox.spec.SpecAnalysis`, for
    #: results written to the results specification.
    spec: dict = field(default_factory=dict)


def _slugify(text: str) -> str:
    """Convert a label to a filesystem-safe slug."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")




# Raster figure formats the gallery copies and thumbnails (Pillow-readable).
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def _read_provenance(analysis_dir: Path) -> dict | None:
    """The analysis's ``provenance.json``, or None when absent/unreadable.

    Written by the analysis package beside its tables: what produced them (the
    package and its version, the subjects, the settings that decide the
    numbers). Older result trees have none, which the gallery shows as
    unrecorded; the profile decides which parts are shown.
    """
    path = analysis_dir / "provenance.json"
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


class ResultsScanner:
    """Scan a results directory (``tables/`` + ``figures/``).

    ``tables/<paradigm>/<analysis>/*.csv`` (with an optional ``provenance.json``
    beside them) and ``figures/<paradigm>/<analysis>/**``. Point it at a subtree
    of a results tree for a run written there — the layout below the root is
    the same.
    """

    def __init__(self, path: Path, label: str):
        self.path = Path(path)
        self.label = label

    def scan(self) -> ScanResult:
        result = ScanResult()

        # Figures: figures/<paradigm>/<analysis>/**/*.{png,jpg,webp}. Nested
        # subfolders are flattened into the filename (a/b.png -> a__b.png) so
        # every figure of a module lives in one gallery folder.
        figs_root = self.path / "figures"
        if figs_root.exists():
            for paradigm_dir in sorted(figs_root.iterdir()):
                if not paradigm_dir.is_dir():
                    continue
                paradigm = paradigm_dir.name
                for analysis_dir in sorted(paradigm_dir.iterdir()):
                    if not analysis_dir.is_dir():
                        continue
                    analysis = analysis_dir.name
                    for fig in sorted(p for p in analysis_dir.rglob("*") if _is_image(p)):
                        rel = fig.relative_to(analysis_dir)
                        result.figures.append(
                            FigureEntry(
                                src_path=fig,
                                category="analytics",
                                source_label=self.label,
                                paradigm=paradigm,
                                analysis=analysis,
                                filename="__".join(rel.parts),
                            )
                        )

        # Tables: tables/<paradigm>/<analysis>/*.csv
        tables_root = self.path / "tables"
        if tables_root.exists():
            for paradigm_dir in sorted(tables_root.iterdir()):
                if not paradigm_dir.is_dir():
                    continue
                paradigm = paradigm_dir.name
                for analysis_dir in sorted(paradigm_dir.iterdir()):
                    if not analysis_dir.is_dir():
                        continue
                    analysis = analysis_dir.name
                    record = _read_provenance(analysis_dir)
                    if record is not None:
                        result.provenance[(paradigm, analysis)] = record
                    for tbl in sorted(analysis_dir.glob("*.csv")):
                        result.tables.append(
                            TableEntry(
                                src_path=tbl,
                                source_label=self.label,
                                paradigm=paradigm,
                                analysis=analysis,
                                filename=tbl.name,
                            )
                        )

        return result


def qc_csv_to_json(csv_path: Path) -> list[dict]:
    """Convert a QC metrics CSV to a list of dicts for JSON serialization."""
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


class SpecScanner:
    """Scan a results root written to the results specification (:mod:`.spec`).

    Every analysis folder under the root becomes one analysis of the gallery:
    grouped by its ``analysis_type`` -- or, when the study declares ``sections``, by
    the first section it matches (:func:`.spec.section_of`) -- named by its ``id``,
    with exactly the tables and figures its ``analysis.json`` lists — nothing is
    picked up by filename.
    """

    def __init__(self, path: Path, label: str, warn=lambda msg: None,
                 sections: list[dict] | None = None):
        self.path = Path(path)
        self.label = label
        self.warn = warn
        self.sections = sections or []

    def scan(self) -> ScanResult:
        from .spec import UNSECTIONED, find_analyses, load_analysis, section_of

        result = ScanResult()
        for folder in find_analyses(self.path):
            spec = load_analysis(folder, self.warn)
            if spec is None:
                continue
            if self.sections:
                paradigm = section_of(spec, self.sections)
                if paradigm == UNSECTIONED:
                    self.warn(f"  NOTE: {spec.id!r} ({spec.analysis_type}) matches no section; "
                              "listed under Other")
            else:
                paradigm = _slugify(spec.analysis_type)
            analysis = _slugify(spec.id)
            key = (paradigm, analysis)
            if key in result.spec:
                self.warn(f"  WARNING: two analyses with id {spec.id!r}; {folder} skipped")
                continue
            result.spec[key] = spec
            if spec.provenance is not None:
                result.provenance[key] = spec.provenance
            seen = set()
            for tbl in spec.tables:
                name = "__".join(tbl.path.relative_to(folder).parts)
                seen.add(name)
                result.tables.append(TableEntry(
                    src_path=tbl.path, source_label=self.label, paradigm=paradigm,
                    analysis=analysis, filename=name,
                    dictionary=tbl.path.with_suffix(".json") if tbl.columns else None))
            for fig in spec.figures():
                path = spec.file(str(fig.get("path", "")))
                if path is None or not _is_image(path):
                    self.warn(f"  WARNING: {folder}: figure {fig.get('path')!r} is not an image "
                              "in the folder")
                    continue
                result.figures.append(FigureEntry(
                    src_path=path, category="analytics", source_label=self.label,
                    paradigm=paradigm, analysis=analysis,
                    filename="__".join(path.relative_to(folder).parts)))
        return result
