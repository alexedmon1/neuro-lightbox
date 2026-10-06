"""Build configuration dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SourceInput:
    """A labeled input directory (results, or an input a profile scans)."""

    path: Path
    label: str

    def __post_init__(self):
        self.path = Path(self.path)


@dataclass
class BuildConfig:
    """Configuration for a gallery build.

    Everything here is the core's; what a kind of study adds (its inputs side,
    its helpers' settings) is the profile's own settings object in ``options``
    — see :mod:`neuro_lightbox.profiles`.
    """

    output_dir: Path
    #: None: the profile's default title.
    title: str | None = None
    results: list[SourceInput] = field(default_factory=list)
    thumb_size: int = 300
    thumb_quality: int = 80
    thumb_workers: int = 4
    max_table_rows: int = 500
    render_figures: bool = True
    figure_dpi: int = 150
    contrasts: list[str] | None = None    # study contrasts to render (None = all)
    contrast_labels: dict | None = None   # contrast name -> readable label
    contrast_groups: dict | None = None   # contrast name -> tier/group label
    contrast_meta: dict | None = None     # contrast name -> {role, test, gate_on}
    contrast_design: dict | None = None   # contrast name -> {group_a, group_b} (two-group)
    # Per-paradigm nav display: paradigm key -> {group, label}. Lets a study nest
    # its paradigms under a shared group header (e.g. resting/vertex -> "Resting"
    # with "ROI-based"/"Vertex-based" sub-labels). None = flat, formatName labels.
    paradigm_display: dict | None = None
    # The study's sections (study YAML ``sections:``, checked by
    # spec.normalize_sections): spec analyses are listed by section, in this order,
    # and a section nothing matches yet is shown as not yet run. None = by
    # analysis_type.
    sections: list[dict] | None = None
    # Treatment-group display: id -> readable label, and the id order to list
    # groups in (both from the study YAML's ``groups:`` / ``group_order:``).
    # None = format the raw id (underscores -> spaces), alphabetical order.
    group_labels: dict | None = None
    group_order: list | None = None
    # Optional "back" link rendered in the sidebar header — used when this gallery is
    # one view under a splash/landing page (e.g. report/ + exploratory/ under a shared
    # index.html). None = self-contained build, no link (so a handed-off standalone
    # build never carries a dead ../index.html).
    home_link: str | None = None
    home_label: str = "Home"
    # Pages beside the results a reader should reach from the gallery (e.g. the
    # preprocessing QC index): [{label, path}] with absolute paths; the sidebar links
    # them relative to the gallery (study.yaml `links:`).
    links: list[dict] | None = None
    # Analyses to omit from the gallery entirely (figures, tables, summaries, nav).
    # None = the profile's default; a study can override via `exclude_analyses:`.
    exclude_analyses: list[str] | None = None
    #: The profile that reads this study's outputs (None: the default profile).
    profile: str | None = None
    #: The profile's own settings (None: its defaults).
    options: object = None

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
