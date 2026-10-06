"""Profiles: what one kind of study brings to the gallery.

The core builds a gallery from any results tree — it scans tables and figures,
renders an overview figure per analysis, writes a digest, embeds the tables and
their provenance, and serves the app. It knows nothing about a domain: not its
category axis, its column names, its inputs, its file conventions or the words a
reader expects. A profile supplies those.

A study selects its profile with ``profile:`` in study.yaml (or ``--profile``);
without one it gets ``eeg``, so every study config written before profiles
existed builds as it did. Built-in profiles are listed below; a package can add
one through the ``neuro_lightbox.profiles`` entry-point group, naming a
:class:`Profile` subclass.

The hooks below are the whole interface. Each has a neutral default, so a
profile overrides only what its domain needs.
"""

from __future__ import annotations

import importlib
from importlib import metadata
from pathlib import Path

DEFAULT = "eeg"
ENTRY_POINT_GROUP = "neuro_lightbox.profiles"
_BUILTIN = {"eeg": "neuro_lightbox.profiles.eeg:EegProfile",
            "mri": "neuro_lightbox.profiles.mri:MriProfile"}


class Profile:
    """The hooks a profile may override. Instances are stateless."""

    #: Name a study selects the profile by.
    name = "base"
    #: Gallery title when neither the study nor the command line names one.
    default_title = "Gallery"
    #: Analyses left out unless the study says otherwise (``exclude_analyses:``).
    default_exclude: tuple = ()
    #: Manifest key of the inputs block (subjects / QC of whatever produced the
    #: data the analyses ran on), or None for a profile without one.
    inputs_key: str | None = None
    #: Columns holding a contrast name, relabelled with the study's labels
    #: before an overview figure is drawn.
    contrast_columns: tuple = ()
    #: Overview renderers, first match wins (see :mod:`neuro_lightbox.render`).
    renderers: tuple = ()

    # -- configuration -------------------------------------------------------
    def options(self):
        """The profile's own build settings, as defaults."""
        return None

    def cli_options(self) -> list:
        """Extra ``click.Option``s for ``build``. Their values reach
        :meth:`read_options` by parameter name."""
        return []

    def input_options(self) -> tuple:
        """Parameter names of the ``cli_options`` that take input folders and pair
        with ``--label``, in the order the labels are applied (before ``--results``)."""
        return ()

    def results_subdir(self, study: dict) -> str | None:
        """Subfolder of each results tree to read, named by the study config."""
        return None

    def read_options(self, cli: dict, study: dict | None, config_dir: Path | None,
                     resolve, contrasts: list[dict], warn, labelled_inputs):
        """Build the profile's settings from its command-line values (``cli``)
        and, when given, the study config. ``resolve(raw, default)`` resolves a
        config path; ``labelled_inputs`` parses a ``paths:`` entry (see
        :func:`neuro_lightbox.cli.labelled_inputs`); ``contrasts`` are the
        study's contrasts, normalised."""
        return self.options()

    # -- scanning ------------------------------------------------------------
    def scan_inputs(self, options, log):
        """Scan the inputs side; returns a :class:`~neuro_lightbox.scanner.ScanResult`."""
        from ..scanner import ScanResult

        return ScanResult()

    def filter_scan(self, scan, options, log) -> None:
        """Drop entries the profile never publishes (in place)."""

    # -- rendering -----------------------------------------------------------
    def table_priority(self, filename: str) -> int:
        """Rank of a table as the source of its analysis's overview figure."""
        return 0

    def render_setup(self, config, options, log):
        """Per-build state for the render hooks (e.g. which helpers are available)."""
        return None

    def render_before(self, group, dest: Path, module: tuple, state, log) -> tuple[list, bool]:
        """Figures drawn before the overview, and whether they replace it."""
        return [], False

    def render_after(self, ranked, chosen, renderer, dest: Path, module: tuple, state, dpi,
                     log) -> list:
        """Figures drawn after the overview, alongside it."""
        return []

    def render_spec(self, spec, dest: Path, dpi: int, log) -> list:
        """Figures of one analysis read from the results specification
        (:class:`~neuro_lightbox.spec.SpecAnalysis`), drawn after the core's
        effect overview; paths of PNGs written under ``dest``."""
        return []

    # -- manifest ------------------------------------------------------------
    def paradigm_labels(self) -> dict:
        """Display names of analysis groups (for specification results: the
        ``analysis_type`` values), unless the study config names them."""
        return {}

    def analysis_meta(self, options, log) -> dict:
        """Per-analysis metadata: ``{name: {domain, supplements, description, about,
        display_name}}``."""
        return {}

    def trim_provenance(self, record: dict) -> dict:
        """The part of an analysis's ``provenance.json`` the gallery shows."""
        return record

    def digest(self, tables: list[dict], full: bool, contrast_labels, contrast_groups,
               contrast_meta, *, contrast_order=None, group_labels=None,
               contrast_design=None) -> str | None:
        """An analysis's digest (HTML), from its tables, or None. ``full`` says the
        tables are complete rather than the gallery's row-capped copies;
        ``contrast_order`` is the study's contrast order, ``group_labels`` names
        its groups, ``contrast_design`` maps a contrast to the two groups it
        compares (``{group_a, group_b}``)."""
        return None

    def descriptive_digest(self, analysis: str, figure_names: list[str],
                           contrast_labels) -> str | None:
        """A digest for an analysis without inferential tables, or None."""
        return None

    def add_inputs(self, block: dict, scan) -> None:
        """Fill the manifest's inputs block from the scan."""

    # -- the app ---------------------------------------------------------------
    def vocabulary(self) -> dict:
        """Words, orders and labels the app reads instead of hard-coding them."""
        return {}

    def assets(self) -> list[Path]:
        """Scripts (``.js``) and styles (``.css``) the app loads after its own."""
        return []

    def app_profile(self) -> dict:
        """What the app is given as ``window.PROFILE``."""
        return {"name": self.name, "vocabulary": self.vocabulary()}


def available() -> dict[str, str]:
    """Profile name -> ``module:Class``, built-ins and installed entry points."""
    found = dict(_BUILTIN)
    try:
        eps = metadata.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:                                   # Python < 3.10 selection API
        eps = metadata.entry_points().get(ENTRY_POINT_GROUP, [])
    for ep in eps:
        found.setdefault(ep.name, ep.value)
    return found


_LOADED: dict[str, Profile] = {}


def get_profile(name: str | None = None) -> Profile:
    """The profile called ``name`` (default: :data:`DEFAULT`)."""
    name = name or DEFAULT
    if name not in _LOADED:
        target = available().get(name)
        if target is None:
            raise ValueError(f"unknown profile {name!r}; available: {', '.join(sorted(available()))}")
        module, _, attr = target.partition(":")
        cls = getattr(importlib.import_module(module), attr)
        _LOADED[name] = cls()
    return _LOADED[name]
