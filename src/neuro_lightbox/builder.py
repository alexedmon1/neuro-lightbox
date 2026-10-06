"""Orchestrate the gallery build: scan, copy, thumbs, HTML, manifest."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import jinja2

from .config import BuildConfig
from .manifest import build_manifest
from .profiles import get_profile
from .scanner import ResultsScanner, ScanResult, SpecScanner, _slugify
from .spec import find_analyses
from .thumbnails import generate_thumbnails


def build(config: BuildConfig, verbose: bool = True) -> Path:
    """Run the full gallery build pipeline.

    Returns the output directory path.
    """
    out = config.output_dir
    _log = print if verbose else lambda *a, **k: None
    profile = get_profile(config.profile)
    options = config.options if config.options is not None else profile.options()
    title = config.title if config.title is not None else profile.default_title

    # 1. Scan all inputs: the profile's inputs side, then the results trees.
    _log("Scanning inputs...")
    scan = ScanResult()
    _merge_scan(scan, profile.scan_inputs(options, _log))

    for res_input in config.results:
        _log(f"  Results: {res_input.path} [{res_input.label}]")
        # A tree written to the results specification is read by what its
        # analysis.json files list; any other tree by its folder layout.
        if find_analyses(res_input.path):
            scanner = SpecScanner(res_input.path, res_input.label, warn=_log)
        else:
            scanner = ResultsScanner(res_input.path, res_input.label)
        partial = scanner.scan()
        _merge_scan(scan, partial)

    # What the profile never publishes goes first and separately, so that a
    # study overriding `exclude_analyses:` cannot bring it back by accident.
    profile.filter_scan(scan, options, _log)

    # Drop excluded analyses (by default the profile's, e.g. superseded aliases)
    # from every scan list — figures AND tables — so they vanish from the
    # manifest, nav, and rendered figures. Also match on paradigm to clear a
    # stray top-level alias paradigm dir.
    excl = set(config.exclude_analyses if config.exclude_analyses is not None
               else profile.default_exclude)

    if excl:
        def _keep(e):
            return e.analysis not in excl and getattr(e, "paradigm", None) not in excl
        n0 = len(scan.figures) + len(scan.tables)
        scan.figures = [e for e in scan.figures if _keep(e)]
        scan.tables = [e for e in scan.tables if _keep(e)]
        n_drop = n0 - (len(scan.figures) + len(scan.tables))
        if n_drop:
            _log(f"  Excluded {n_drop} entries from {sorted(excl)}")

    _log(f"  Found: {len(scan.figures)} figures, {len(scan.tables)} tables")

    # 2. Prepare output directory. Rendered analytics figures are regenerated
    #    every build, so clear stale ones (and their thumbnails) to avoid orphans
    #    from a prior run. Input-side figures are stable and kept.
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("figures/analytics", "figures/thumbs/analytics", "qc", "tables"):
        shutil.rmtree(out / sub, ignore_errors=True)

    # 2b. Render standardized figures from tables (staged, then treated like any
    #     other discovered figure by the copy/thumbnail/manifest steps below).
    staging_dir = out / ".rendered"
    legacy_tables = [t for t in scan.tables if (t.paradigm, t.analysis) not in scan.spec]
    if config.render_figures and scan.spec:
        _log("Rendering figures of specification analyses...")
        from .spec_render import render_spec_figures

        from .spec import StudyNames

        names = StudyNames(dict(config.contrast_labels or {}), list(config.contrasts or []))
        rendered = render_spec_figures(scan, staging_dir, config.figure_dpi, profile, _log, names)
        scan.figures.extend(rendered)
        _log(f"  Rendered {len(rendered)} figures for {len(scan.spec)} analyses")
    if config.render_figures and legacy_tables:
        _log("Rendering figures from tables...")
        from .render import render_table_figures

        rendered = render_table_figures(
            legacy_tables, staging_dir, dpi=config.figure_dpi, log=_log, profile=profile,
            state=profile.render_setup(config, options, _log),
            contrast_labels=config.contrast_labels, contrast_order=config.contrasts,
        )
        scan.figures.extend(rendered)
        _log(f"  Rendered {len(rendered)} figures from {len(scan.tables)} tables")

    # 3. Copy figures
    _log("Copying figures...")
    for fig in scan.figures:
        dst = out / "figures" / fig.gallery_rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fig.src_path, dst)

    # 3b. Copy tables verbatim so the UI can offer the full CSV (the inline copy
    #     embedded in the manifest is row-capped for display).
    _log("Copying tables...")
    for tbl in scan.tables:
        dst = out / tbl.gallery_rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tbl.src_path, dst)
        if tbl.dictionary is not None:                 # the column dictionary travels with it
            shutil.copy2(tbl.dictionary, dst.with_suffix(".json"))

    # 4. Process QC report (a full self-contained HTML page). Namespace by source
    #    slug so multiple input sources (e.g. two pipelines) don't collide.
    for qc in scan.qc_entries:
        if qc.report_path:
            qc_out = out / "qc" / _slugify(qc.source_label)
            qc_out.mkdir(parents=True, exist_ok=True)
            shutil.copy2(qc.report_path, qc_out / "qc_report.html")

    # 5. Generate thumbnails
    _log("Generating thumbnails...")
    thumb_tasks = []
    for fig in scan.figures:
        src = out / "figures" / fig.gallery_rel_path
        dst = out / "figures" / fig.thumb_rel_path
        thumb_tasks.append((src, dst))

    def _progress(done, total):
        if done % 50 == 0 or done == total:
            _log(f"  Thumbnails: {done}/{total}")

    errors = generate_thumbnails(
        thumb_tasks,
        size=config.thumb_size,
        quality=config.thumb_quality,
        workers=config.thumb_workers,
        on_progress=_progress,
    )
    if errors:
        for err in errors:
            _log(f"  WARNING: {err}")

    # 6. Build manifest (tables + summaries are embedded inline)
    _log("Building manifest...")
    analysis_meta = profile.analysis_meta(options, _log)
    manifest = build_manifest(
        scan, title, max_table_rows=config.max_table_rows,
        contrast_labels=config.contrast_labels,
        contrast_groups=config.contrast_groups,
        contrast_meta=config.contrast_meta,
        analysis_meta=analysis_meta,
        paradigm_display=config.paradigm_display,
        group_labels=config.group_labels,
        group_order=config.group_order,
        profile=profile,
        contrast_order=config.contrasts,
        contrast_design=config.contrast_design,
    )
    manifest_json = json.dumps(manifest, indent=2)
    data_dir = out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "manifest.json").write_text(manifest_json, encoding="utf-8")
    # The profile's vocabulary, beside the manifest: the words and orders the app
    # shows this gallery's data in (the manifest itself is the data).
    profile_json = json.dumps(profile.app_profile(), indent=2)
    (data_dir / "profile.json").write_text(profile_json, encoding="utf-8")

    # 7. Render HTML
    _log("Rendering HTML...")
    assets = profile.assets()
    _render_html(out, manifest_json, title=title,
                 home_link=config.home_link, home_label=config.home_label,
                 profile_json=profile_json,
                 scripts=[p.name for p in assets if p.suffix == ".js"],
                 styles=[p.name for p in assets if p.suffix == ".css"])

    # 8. Copy static assets
    _log("Copying static assets...")
    _copy_static(out, extra=assets)

    # 9. Clean up staged renders (already copied into figures/ above)
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)

    _log(f"Gallery built: {out}")
    _log(f"  {manifest['stats']['total_figures']} figures")
    _log(f"  {manifest['stats']['total_tables']} tables")
    _log(f"  {manifest['stats']['total_summaries']} summaries")

    return out


def _merge_scan(target: ScanResult, source: ScanResult):
    """Merge source scan results into target."""
    target.figures.extend(source.figures)
    target.tables.extend(source.tables)
    target.qc_entries.extend(source.qc_entries)
    target.runs.update(source.runs)
    target.provenance.update(source.provenance)
    target.spec.update(source.spec)


def _render_html(out: Path, manifest_json: str, title: str = "Gallery",
                 home_link: str | None = None, home_label: str = "Home",
                 profile_json: str = "{}", scripts=(), styles=()):
    """Render the index.html from the Jinja2 template."""
    template_dir = Path(__file__).parent / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    template = env.get_template("index.html.j2")
    html = template.render(
        # Inlined in a <script>: neither "</" nor "<!--" may appear there as is.
        manifest_json=_script_safe(manifest_json),
        title=title,
        build_ts=str(int(time.time())),
        home_link=home_link,
        home_label=home_label,
        profile_json=_script_safe(profile_json),
        profile_scripts=list(scripts),
        profile_styles=list(styles),
    )
    (out / "index.html").write_text(html, encoding="utf-8")


def _script_safe(text: str) -> str:
    """JSON that can sit inside a <script> element: ``</`` and ``<!--`` escaped
    (``<\\/``, ``\\u003c!--``), which leaves the JSON's meaning unchanged."""
    return text.replace("</", "<\\/").replace("<!--", "\\u003c!--")


def _copy_static(out: Path, extra=()):
    """Copy vendored static assets to output, and the profile's (``extra``)."""
    static_src = Path(__file__).parent / "static"
    for path in extra:
        dst_dir = out / "assets" / path.suffix.lstrip(".")
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst_dir / path.name)
    if not static_src.exists():
        return

    assets_dir = out / "assets"
    for sub in ("css", "js"):
        src_dir = static_src / sub
        if not src_dir.exists():
            continue
        dst_dir = assets_dir / sub
        dst_dir.mkdir(parents=True, exist_ok=True)
        for f in src_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, dst_dir / f.name)
