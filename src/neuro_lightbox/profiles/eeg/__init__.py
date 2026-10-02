"""The EEG profile: source-analytics results, source-localization inputs.

Everything source-lightbox knew about EEG source analysis, behind the profile
interface (:class:`neuro_lightbox.profiles.Profile`):

- :mod:`.cli` — the build options and study-config keys (localizations, the
  source-analytics interpreter and working tree, ROI categories, atlas);
- :mod:`.inputs` — source-localization pipelines: subjects, QC, run settings;
- :mod:`.render` — renderers over source-analytics' table schema, frequency-band
  order, table ranking, and the mosaic / circos helpers
  (:mod:`.brain_mosaic`, :mod:`.circos` and their workers);
- :mod:`.summarize` — the digest builders;
- :mod:`.source_analytics` — analysis metadata, provenance trimming, retired
  analyses;
- :mod:`.vocabulary` and ``static/`` — the words, orders, and page behaviour the
  app takes from this profile.

It is the default profile: a study config without ``profile:`` builds with it.
"""

from __future__ import annotations

from pathlib import Path

from .. import Profile
from . import cli as _cli
from . import inputs as _inputs
from .cli import EegOptions  # noqa: F401  (the profile's settings type)
from .source_analytics import DEFAULT_EXCLUDE

STATIC = Path(__file__).parent / "static"


class EegProfile(Profile):
    name = "eeg"
    default_title = "Source Analysis Gallery"
    default_exclude = DEFAULT_EXCLUDE
    inputs_key = _inputs.CATEGORY
    contrast_columns = ("contrast", "hypothesis")  # native, and the legacy alias

    @property
    def renderers(self):
        from .render import REGISTRY

        return REGISTRY

    # -- configuration -------------------------------------------------------
    def options(self):
        return EegOptions()

    def cli_options(self):
        return _cli.options()

    def input_options(self):
        return ("localizations",)

    def results_subdir(self, study):
        return _cli.sa_profile(study)

    def read_options(self, cli, study, config_dir, resolve, contrasts, warn, labelled_inputs):
        return _cli.read_options(cli, study, config_dir, resolve, contrasts, warn,
                                 labelled_inputs)

    # -- scanning ------------------------------------------------------------
    def scan_inputs(self, options, log):
        from ...scanner import ScanResult

        scan = ScanResult()
        for loc_input in options.localizations:
            log(f"  Localization: {loc_input.path} [{loc_input.label}]")
            partial = _inputs.LocalizationScanner(loc_input.path, loc_input.label).scan()
            scan.figures.extend(partial.figures)
            scan.tables.extend(partial.tables)
            scan.qc_entries.extend(partial.qc_entries)
            scan.runs.update(partial.runs)
            scan.provenance.update(partial.provenance)
        return scan

    def filter_scan(self, scan, options, log):
        from .source_analytics import filter_retired

        if options.analytics_dir:
            # The analytics working tree is only consulted for the per-subject
            # connectivity edge CSVs the circos average their chords from; the
            # Summary tab is a digest generated from the published tables.
            log(f"  Analytics (edge CSVs for circos): {options.analytics_dir}")
        filter_retired(scan, options.include_retired, log)

    # -- rendering -----------------------------------------------------------
    def table_priority(self, filename):
        from .render import _table_priority

        return _table_priority(filename)

    def render_setup(self, config, options, log):
        from .render import render_state

        # roi_categories is the study's map (a path or an inline mapping) or None, in
        # which case the workers use the study atlas's own category file.
        brain = None
        if options.brain_render:
            brain = {
                "categories": options.roi_categories,
                "atlas": options.atlas,
                "contrasts": config.contrasts,
                "labels": config.contrast_labels,
                "python": options.brain_python,
                "power_type": options.brain_power_type,
            }

        circos = None
        if options.circos_render and options.analytics_dir and options.contrast_pairs:
            circos = {
                "analytics_dir": str(options.analytics_dir),
                "contrasts": options.contrast_pairs,
                "labels": config.contrast_labels,
                "metrics": options.circos_metrics,
                "categories": options.roi_categories,
                "atlas": options.atlas,
                "python": options.brain_python,
            }
        return render_state(brain, circos, config.contrast_labels, log,
                            contrast_order=config.contrasts)

    def render_before(self, group, dest, module, state, log):
        from .render import render_before

        return render_before(group, dest, module, state, log)

    def render_after(self, ranked, chosen, renderer, dest, module, state, dpi, log):
        from .render import render_after

        return render_after(ranked, chosen, renderer, dest, module, state, dpi, log)

    # -- manifest ------------------------------------------------------------
    def analysis_meta(self, options, log):
        from .source_analytics import read_analysis_meta

        return read_analysis_meta(options.brain_python, log=log)

    def trim_provenance(self, record):
        from .source_analytics import trim_provenance

        return trim_provenance(record)

    def digest(self, tables, full, contrast_labels, contrast_groups, contrast_meta, *,
               contrast_order=None, group_labels=None, contrast_design=None):
        from .summarize import build_significance_summary

        # Connectivity's protected post-hocs read the module's region-pair table,
        # in full (the last one, when a module has several).
        region_pair = None
        if full:
            for t in tables:
                if "region_pair" in t["filename"]:
                    region_pair = {"headers": t["headers"], "rows": t["rows"]}
        return build_significance_summary(
            tables, contrast_labels=contrast_labels, contrast_groups=contrast_groups,
            contrast_meta=contrast_meta, region_pair_table=region_pair,
            contrast_order=contrast_order, group_labels=group_labels,
            contrast_design=contrast_design)

    def descriptive_digest(self, analysis, figure_names, contrast_labels):
        # Descriptive-only matrix modules (e.g. roi_connectivity, whose per-edge
        # stats were retired) have no stat tables → no significance digest: a
        # descriptive metric/band digest from the figure names, pointing to the
        # inferential siblings.
        from .summarize import build_descriptive_matrix_summary

        return build_descriptive_matrix_summary(analysis, figure_names,
                                                contrast_labels=contrast_labels)

    def add_inputs(self, block, scan):
        _inputs.add_inputs(block, scan)

    # -- the app ---------------------------------------------------------------
    def vocabulary(self):
        from .vocabulary import VOCABULARY

        return VOCABULARY

    def assets(self):
        return [STATIC / "eeg.js", STATIC / "eeg.css"]
