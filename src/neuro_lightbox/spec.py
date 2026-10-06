"""Reading results written to the results specification.

The specification (``spec: "neurofaune.results"``) is owned by the analysis
package that writes it; this module is one reader of it and knows only the
format: an analysis folder holds ``analysis.json`` (what the analysis is, the
correction and what it is over, the effect measure, what one row of each table
is), ``provenance.json``, and tables with a column dictionary beside each, whose
columns map to a standard vocabulary (``effect_size``, ``p_value``, …). Nothing
here is inferred from a column name, a filename or a folder.

A field this reader does not know is ignored, never guessed at; a folder whose
specification version has a major version this reader was not written for is
skipped with a warning.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

SPEC = "neurofaune.results"
READS_MAJOR = 0
READS_MINOR = 1
TABLE_SUFFIXES = {".csv": ",", ".tsv": "\t"}


@dataclass
class SpecTable:
    """One table an analysis lists, with its column dictionary."""

    path: Path
    role: str
    rows_are: str
    description: str
    headline: bool = False
    columns: dict = field(default_factory=dict)

    def standard(self) -> dict[str, str]:
        """Standard term -> the column that carries it."""
        return {m["Standard"]: c for c, m in self.columns.items()
                if isinstance(m, dict) and m.get("Standard")}

    def qualifier(self, term: str, key: str):
        col = self.standard().get(term)
        return (self.columns.get(col) or {}).get(key) if col else None

    def read(self) -> tuple[list[str], list[dict[str, str]]]:
        with open(self.path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter=TABLE_SUFFIXES[self.path.suffix.lower()])
            rows = list(reader)
            return list(reader.fieldnames or []), rows


@dataclass
class SpecAnalysis:
    """An analysis folder, read."""

    folder: Path
    record: dict
    provenance: dict | None
    tables: list[SpecTable]

    @property
    def id(self) -> str:
        return str(self.record.get("id") or self.folder.name)

    @property
    def analysis_type(self) -> str:
        return str(self.record.get("analysis_type") or "other")

    @property
    def measures(self) -> list[str]:
        return [str(m) for m in self.record.get("measures") or []]

    def tables_with_role(self, role: str) -> list[SpecTable]:
        return [t for t in self.tables if t.role == role]

    def maps(self, kind: str | None = None) -> list[dict]:
        return [m for m in self.record.get("maps") or []
                if isinstance(m, dict) and (kind is None or m.get("kind") == kind)]

    def figures(self) -> list[dict]:
        return [f for f in self.record.get("figures") or [] if isinstance(f, dict)]

    def file(self, rel: str) -> Path | None:
        """A listed file, when it is inside the folder and on disk."""
        p = PurePosixPath(rel)
        if p.is_absolute() or ".." in p.parts:
            return None
        full = self.folder / rel
        return full if full.is_file() else None

    @property
    def alpha(self) -> float:
        corr = (self.record.get("inference") or {}).get("correction") or {}
        try:
            return float(corr.get("alpha", 0.05))
        except (TypeError, ValueError):
            return 0.05


def _json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def is_analysis(folder: Path) -> bool:
    record = _json(Path(folder) / "analysis.json")
    return bool(record) and record.get("spec") == SPEC


def find_analyses(root: Path) -> list[Path]:
    """Every analysis folder at or under ``root``, sorted."""
    root = Path(root)
    if not root.exists():
        return []
    if is_analysis(root):
        return [root]
    return sorted(p.parent for p in root.rglob("analysis.json") if is_analysis(p.parent))


def readable(version: str) -> bool:
    try:
        major, minor = (int(x) for x in str(version).split(".")[:2])
    except ValueError:
        return False
    return major == READS_MAJOR and (major > 0 or minor == READS_MINOR)


def load_analysis(folder: Path, warn=lambda msg: None) -> SpecAnalysis | None:
    """The analysis in ``folder``, or None (with a warning) when it cannot be read."""
    folder = Path(folder)
    record = _json(folder / "analysis.json")
    if not record or record.get("spec") != SPEC:
        return None
    if not readable(record.get("spec_version", "")):
        warn(f"  WARNING: {folder}: specification version {record.get('spec_version')!r} "
             f"is not one this gallery reads; skipped")
        return None
    tables = []
    for entry in record.get("tables") or []:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("path", ""))
        p = PurePosixPath(rel)
        path = folder / rel
        if (not rel or p.is_absolute() or ".." in p.parts or not path.is_file()
                or path.suffix.lower() not in TABLE_SUFFIXES):
            warn(f"  WARNING: {folder}: table {rel!r} is not a readable table in the folder")
            continue
        columns = _json(path.with_suffix(".json")) or {}
        if not columns:
            warn(f"  WARNING: {folder}: table {rel!r} has no column dictionary")
        tables.append(SpecTable(path=path, role=str(entry.get("role", "other")),
                                rows_are=str(entry.get("rows", "")),
                                description=str(entry.get("description", "")),
                                headline=bool(entry.get("headline")), columns=columns))
    return SpecAnalysis(folder=folder, record=record, provenance=_json(folder / "provenance.json"),
                        tables=tables)


def as_float(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if x == x else None                       # NaN is missing


def as_bool(value) -> bool | None:
    s = str(value).strip().lower()
    return True if s in ("true", "1") else False if s in ("false", "0") else None
