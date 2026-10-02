"""The EEG profile's settings: its ``build`` options and the study-config keys it reads.

Inputs are source-localization pipelines (``--localization`` /
``paths.localizations``); the helpers are source-analytics' interpreter (brain
mosaics, connectivity circos, analysis metadata) and its working tree (the edge
CSVs the circos average). A study config is source-analytics' own
``study.yaml``; this reads the subset the gallery needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import click

from ...config import SourceInput


@dataclass
class EegOptions:
    """The EEG profile's build settings."""

    localizations: list[SourceInput] = field(default_factory=list)
    analytics_dir: Path | None = None
    # Anatomy-aware ROI brain mosaics (delegated to source-analytics).
    brain_render: bool = True
    brain_python: str | None = None       # path to source-analytics venv python
    roi_categories: str | dict | None = None  # YAML path, or the study's inline roi_categories: map
    atlas: str | None = None              # the study's pipeline.atlas (categories + mosaic labels)
    brain_power_type: str = "relative"    # power_type filter for ROI mosaics
    # Connectivity circos (delegated to source-analytics)
    circos_render: bool = True
    contrast_pairs: list | None = None    # [{name, group_a, group_b}] for circos
    circos_metrics: list | None = None    # connectivity metrics to render (None = imag_coherence)
    # Render the retired vertex analyses when an old results tree still carries
    # them. Off by default: see source_analytics.RETIRED_ANALYSES. Set for a study
    # that installed source-analytics-vertex and means to publish its output.
    include_retired: bool = False

    def __post_init__(self):
        if self.analytics_dir is not None:
            self.analytics_dir = Path(self.analytics_dir)


def options() -> list[click.Option]:
    return [
        click.Option(
            ["--localization", "localizations"], multiple=True,
            type=click.Path(exists=True, file_okay=False),
            help="Localization output directory (repeatable, pair with --label)."),
        click.Option(
            ["--analytics"], type=click.Path(exists=True, file_okay=False),
            help="source-analytics working directory (paths.analytics). Only its per-subject "
                 "connectivity edge CSVs are read, for the circos chords."),
        click.Option(
            ["--brain/--no-brain", "brain_render"], default=True,
            help="Render anatomy-aware ROI brain mosaics via source-analytics when available."),
        click.Option(["--brain-python"], default=None,
                     help="Path to the source-analytics venv python."),
        click.Option(
            ["--roi-categories"], default=None, type=click.Path(dir_okay=False),
            help="YAML with a top-level roi_categories: mapping (for brain mosaics)."),
        click.Option(
            ["--include-retired"], is_flag=True, default=False,
            help="Publish the retired vertex analyses when an old results tree still carries "
                 "them. They left source-analytics in v0.8.0 for the unmaintained "
                 "source-analytics-vertex plugin."),
    ]


def sa_profile(study: dict) -> str | None:
    """The source-analytics run profile a study builds from: ``--profile NAME``
    runs write to results/<NAME>/ and analytics/<NAME>/, and
    ``paths.results_profile`` (or ``gallery_profile``) selects that subtree.
    Not to be confused with the gallery's own ``profile:`` (this one is ``eeg``)."""
    paths = study.get("paths", {})
    return paths.get("results_profile") or study.get("gallery_profile")


def read_options(cli: dict, study: dict | None, config_dir: Path | None, resolve,
                 contrasts: list[dict], warn, labelled_inputs) -> EegOptions:
    """Command-line values first, then the study config, as source-lightbox did."""
    opts = EegOptions(
        localizations=list(cli.get("localizations") or []),
        analytics_dir=cli.get("analytics"),
        brain_render=cli.get("brain_render", True),
        brain_python=cli.get("brain_python"),
        roi_categories=cli.get("roi_categories"),
        include_retired=bool(cli.get("include_retired")),
    )
    if study is None:
        return opts

    paths = study.get("paths", {})
    profile = sa_profile(study)
    cfg_analytics = resolve(paths.get("analytics"), "./analytics")
    if profile:
        cfg_analytics = str(Path(cfg_analytics) / str(profile))

    # Localization pipelines are a source namespace like the results: each may
    # be a list of {path, label} (to compare reconstructions) or a scalar.
    loc_spec = paths.get("localizations") or paths.get("localization")
    config_loc_inputs = labelled_inputs(loc_spec, "./localization", "Localization",
                                        loc_spec is not None)

    if opts.analytics_dir is None and Path(cfg_analytics).is_dir():
        opts.analytics_dir = Path(cfg_analytics)
    # Contrast name + groups (for connectivity circos).
    opts.contrast_pairs = [
        {"name": c["name"], "group_a": c["group_a"], "group_b": c["group_b"]}
        for c in contrasts if c.get("group_a") and c.get("group_b")
    ] or None
    cm = study.get("circos_metrics")
    opts.circos_metrics = list(cm) if cm else None
    opts.include_retired = opts.include_retired or bool(study.get("include_retired"))
    # ROI categories: an explicit YAML path, else the study's own inline map (the one
    # source-analytics analysed with; a profile's narrowing for a profile build), else
    # the conventional file beside the config. Left None, the render workers fall
    # back to the study atlas's own category file.
    if opts.roi_categories is None:
        cfg_cats = paths.get("roi_categories")
        prof_block = study.get(str(profile)) if profile else None
        study_cats = prof_block.get("roi_categories") if isinstance(prof_block, dict) else None
        study_cats = study_cats or study.get("roi_categories")
        if cfg_cats:
            opts.roi_categories = resolve(cfg_cats, "")
        elif isinstance(study_cats, dict) and study_cats:
            opts.roi_categories = {cat: list(rois) for cat, rois in study_cats.items()}
        else:
            default_cats = config_dir / "allen_roi_categories_proposed.yaml"
            if default_cats.is_file():
                opts.roi_categories = str(default_cats)
    if opts.brain_python is None:
        bp = paths.get("source_analytics_python")
        if bp:
            opts.brain_python = resolve(bp, "")
            if not Path(opts.brain_python).is_file():
                warn(f"WARNING: paths.source_analytics_python is not a file: "
                     f"{opts.brain_python} (mosaics, circos and analysis metadata "
                     "will be unavailable)")
    # The study's atlas (`pipeline.atlas`): the render workers categorise and draw
    # with its own files instead of defaulting to allen32.
    opts.atlas = (study.get("pipeline") or {}).get("atlas") or None

    # Fall back to config-provided labeled inputs when none given on the CLI.
    if not opts.localizations and config_loc_inputs:
        opts.localizations = config_loc_inputs
    return opts
