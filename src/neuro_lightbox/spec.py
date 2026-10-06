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


@dataclass
class StudyNames:
    """The study config's names and order for tests (study.yaml ``contrasts``).

    A test is (facet, contrast). Its label is looked up as ``"facet · contrast"``, then
    ``"facet__contrast"`` (a whole-test label), else the facet and the contrast are each
    relabelled on their own; anything without a label keeps its own name. Tests the
    config lists come in its order, the rest after, in their own order.
    """

    labels: dict = field(default_factory=dict)
    order: list = field(default_factory=list)

    def _whole(self, facet: str, contrast: str) -> str | None:
        for key in (f"{facet} · {contrast}", f"{facet}__{contrast}"):
            if facet and key in self.labels:
                return key
        return None

    def label(self, facet: str, contrast: str) -> str:
        whole = self._whole(facet, contrast)
        if whole:
            return str(self.labels[whole])
        parts = [self.labels.get(facet, facet), self.labels.get(contrast, contrast)]
        return " · ".join(str(p) for p in parts if p)

    def contrast(self, contrast: str) -> str:
        return str(self.labels.get(contrast, contrast))

    def rank(self, facet: str, contrast: str) -> int:
        rank = {n: i for i, n in enumerate(self.order)}
        for key in (f"{facet} · {contrast}", f"{facet}__{contrast}", contrast, facet):
            if key in rank:
                return rank[key]
        return len(self.order)


# ── Sections: the study's grouping of its analyses ─────────────────────────────
#
# The specification says what an analysis is (``analysis_type``, ``modality``,
# ``measures``, ``id``); how a study wants its gallery divided is the study's, so
# it is declared in the gallery config (``sections:``), not in analysis.json. An
# analysis is filed under the first section whose ``match`` it meets; one that
# meets none is listed under UNSECTIONED, never dropped. A section nothing meets
# yet is still shown, as not yet run, with its note.

UNSECTIONED = "unsectioned"
UNSECTIONED_LABEL = "Matching no section"
UNSECTIONED_GROUP = "Other"
MATCH_KEYS = ("analysis_type", "modality", "measures", "id_prefix")


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def _one_of(value) -> list[str]:
    return [str(v) for v in (value if isinstance(value, list) else [value])]


def normalize_sections(raw) -> list[dict]:
    """The config's ``sections:`` list, checked: ``[{key, label, group, note, match}]``.

    ``label`` and a non-empty ``match`` are required; ``key`` defaults to the label's
    slug. ``match`` keys (all must hold): ``analysis_type``, ``modality`` (a value or
    a list of them), ``measures`` (any one of them, case-insensitive), ``id_prefix``.
    Raises ValueError on anything else, so a typo does not silently empty a section.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("sections: must be a list")
    out, seen = [], set()
    for i, s in enumerate(raw):
        if not isinstance(s, dict) or not s.get("label"):
            raise ValueError(f"sections[{i}]: needs a label")
        key = _slug(s.get("key") or s["label"])
        if not key or key == UNSECTIONED or key in seen:
            raise ValueError(f"sections[{i}] ({s['label']!r}): key {key!r} is empty, reserved or repeated")
        match = s.get("match")
        if not isinstance(match, dict) or not match:
            raise ValueError(f"sections[{i}] ({s['label']!r}): needs a match")
        unknown = set(match) - set(MATCH_KEYS)
        if unknown:
            raise ValueError(f"sections[{i}] ({s['label']!r}): unknown match key(s) {sorted(unknown)}; "
                             f"known: {', '.join(MATCH_KEYS)}")
        seen.add(key)
        out.append({"key": key, "label": str(s["label"]),
                    "group": str(s["group"]) if s.get("group") else None,
                    "note": str(s["note"]) if s.get("note") else None,
                    "match": {k: _one_of(v) for k, v in match.items()}})
    return out


def section_matches(analysis: SpecAnalysis, match: dict) -> bool:
    """Whether an analysis meets every condition of a section's match."""
    if "analysis_type" in match and analysis.analysis_type not in match["analysis_type"]:
        return False
    if "modality" in match and str(analysis.record.get("modality") or "") not in match["modality"]:
        return False
    if "measures" in match:
        want = {m.lower() for m in match["measures"]}
        if not want & {m.lower() for m in analysis.measures}:
            return False
    if "id_prefix" in match and not any(analysis.id.startswith(p) for p in match["id_prefix"]):
        return False
    return True


def section_of(analysis: SpecAnalysis, sections: list[dict]) -> str:
    """The key of the first section the analysis meets, else UNSECTIONED."""
    for s in sections:
        if section_matches(analysis, s["match"]):
            return s["key"]
    return UNSECTIONED
