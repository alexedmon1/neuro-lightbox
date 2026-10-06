"""Click CLI for neuro-lightbox: build, serve, info."""

from __future__ import annotations

import http.server
import json
import socketserver
import sys
from functools import partial
from pathlib import Path

import click

from .config import BuildConfig, SourceInput
from .profiles import DEFAULT as DEFAULT_PROFILE
from .profiles import available, get_profile


def normalize_study_contrasts(study_cfg: dict) -> list[dict]:
    """Return the study's contrasts as uniform dicts, from either schema.

    Legacy studies declare ``contrasts:``; migrated studies declare
    ``hypotheses:`` (name/label/role/kind/weights). Both are normalized to the
    shape the per-contrast figure and label plumbing expects: ``name``, ``label``,
    ``role``, ``group`` (role doubles as the tier label), and ``group_a`` /
    ``group_b`` derived from the +1 / -1 entries of a two-group contrast's
    ``weights``. ``contrasts:`` takes precedence when present.
    """
    legacy = [c for c in (study_cfg.get("contrasts") or [])
              if isinstance(c, dict) and c.get("name")]
    if legacy:
        return legacy
    out: list[dict] = []
    for h in (study_cfg.get("hypotheses") or []):
        if not isinstance(h, dict) or not h.get("name"):
            continue
        weights = h.get("weights") or {}
        pos = [g for g, w in weights.items() if isinstance(w, (int, float)) and w > 0]
        neg = [g for g, w in weights.items() if isinstance(w, (int, float)) and w < 0]
        norm = {
            "name": h["name"],
            "label": h.get("label"),
            "role": h.get("role"),
            "group": h.get("role"),
        }
        if len(pos) == 1 and len(neg) == 1:
            norm["group_a"], norm["group_b"] = pos[0], neg[0]
        out.append(norm)
    return out


def resolve_config_path(raw: str | None, default: str, config_dir: Path) -> str:
    """Resolve a ``paths:`` entry from the study YAML.

    ``~`` is expanded first (the README documents interpreter paths written
    as ``~/sandbox/.../python``), then relative paths are taken relative to the
    YAML's directory.
    """
    pp = Path(raw or default).expanduser()
    resolved = pp if pp.is_absolute() else (config_dir / pp).resolve()
    return str(resolved)


def study_group_display(study_cfg: dict) -> tuple[dict | None, list | None]:
    """``(group_labels, group_order)`` from the study YAML's ``groups:`` block.

    A study declares ``groups: {id: label}`` (or a list of ``{name/id, label}``)
    plus an optional ``group_order:``. Returns ``(None, None)`` when the study
    declares neither.
    """
    raw = study_cfg.get("groups")
    labels: dict = {}
    if isinstance(raw, dict):
        labels = {str(k): (str(v) if isinstance(v, str) else str((v or {}).get("label") or k))
                  for k, v in raw.items()}
    elif isinstance(raw, list):
        for g in raw:
            if isinstance(g, dict):
                gid = g.get("name") or g.get("id")
                if gid:
                    labels[str(gid)] = str(g.get("label") or gid)
            elif isinstance(g, str):
                labels[g] = g
    order = study_cfg.get("group_order")
    order = [str(g) for g in order] if isinstance(order, list) else (list(labels) or None)
    return (labels or None), order


def labelled_inputs(spec, scalar_default, scalar_label, explicit, *, resolve, sub=None):
    """Parse a ``paths:`` entry that is either a list of {path, label} (compared
    sources, e.g. two reconstructions) or a single scalar path. Configured paths
    that are not directories are reported (a typo otherwise builds a quietly
    incomplete gallery); only the implicit default is skipped silently. ``sub``
    appends a subdirectory (a run written below the configured root)."""
    out = []
    entries = spec if isinstance(spec, list) else [spec]
    for entry in entries:
        if isinstance(entry, dict):
            p = resolve(entry.get("path"), scalar_default)
            lbl = entry.get("label") or Path(p).name
        else:
            p = resolve(entry, scalar_default)
            lbl = (scalar_label if not isinstance(spec, list) else None) or Path(p).name
        if sub:
            p = str(Path(p) / sub)
        if Path(p).is_dir():
            out.append(SourceInput(path=p, label=lbl))
        elif explicit:
            click.echo(f"WARNING: configured path is not a directory, skipping: {p}",
                       err=True)
    return out


def _profile_options() -> list[click.Option]:
    """Every installed profile's ``build`` options (each named once)."""
    seen: set[str] = set()
    out: list[click.Option] = []
    for name in available():
        try:
            options = get_profile(name).cli_options()
        except Exception as exc:  # noqa: BLE001 - a broken plugin must not break the CLI
            click.echo(f"WARNING: profile {name!r} unavailable: {exc}", err=True)
            continue
        for opt in options:
            if opt.name not in seen:
                seen.add(opt.name)
                out.append(opt)
    return out


@click.group()
@click.version_option()
def main():
    """neuro-lightbox: static gallery builder for neuro study results."""
    pass


@main.command()
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True, dir_okay=False),
    help="Unified study.yaml — auto-populates the results and the profile's inputs from "
         "its paths section.",
)
@click.option(
    "--profile",
    "profile_name",
    default=None,
    help=f"The profile that reads the outputs (default: the study config's `profile:`, "
         f"else {DEFAULT_PROFILE}).",
)
@click.option(
    "--results",
    "results_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False),
    help="Results directory (repeatable, pair with --label).",
)
@click.option(
    "--label",
    "labels",
    multiple=True,
    help="Label for the preceding input or --results directory (applied in order: the "
         "profile's inputs first, then --results).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output gallery directory.",
)
@click.option("--title", default=None, help="Gallery title.")
@click.option("--thumb-size", default=300, type=int, help="Thumbnail max dimension.")
@click.option("--thumb-quality", default=80, type=int, help="Thumbnail JPEG quality.")
@click.option("--thumb-workers", default=4, type=int, help="Parallel thumbnail workers.")
@click.option(
    "--render-figures/--no-render-figures",
    default=True,
    help="Render standardized figures from stat tables at build time.",
)
@click.option("--figure-dpi", default=150, type=int, help="DPI for rendered figures.")
@click.option("--exclude-analysis", "exclude_analyses", multiple=True,
              help="Analysis name to omit from the gallery (repeatable). Overrides "
                   "the study config's exclude_analyses / the profile's default.")
@click.option("--home-link", default=None,
              help="Relative URL to a splash/landing page, rendered as a 'back' link in "
                   "the sidebar (e.g. ../index.html when this gallery is a view under a "
                   "splash). Omit for a self-contained standalone build.")
@click.option("--home-label", default="Home",
              help="Text for the --home-link back link.")
@click.option("--verbose/--quiet", default=True, help="Verbose output.")
@click.option("--serve", "serve_after", is_flag=True, default=False,
              help="Serve the gallery locally after building (build + preview in one step).")
@click.option("--port", "-p", default=5500, type=int, help="Port for --serve.")
@click.pass_context
def build(
    ctx,
    config_file,
    profile_name,
    results_dirs,
    labels,
    output,
    title,
    thumb_size,
    thumb_quality,
    thumb_workers,
    render_figures,
    figure_dpi,
    exclude_analyses,
    home_link,
    home_label,
    verbose,
    serve_after,
    port,
    **profile_cli,
):
    """Build a static gallery from analysis outputs.

    Options after --port belong to a profile; each applies when that profile
    reads the study.
    """
    import yaml as _yaml

    # Study contrasts that drive the per-contrast figures (read from --config).
    contrasts = None
    # Contrast name -> readable label / tier group (read from --config).
    contrast_labels = None
    contrast_groups = None
    # Contrast name -> {role, test, gate_on} hypothesis metadata (read from --config).
    contrast_meta = None
    # Contrast name -> the two groups it compares (read from --config).
    contrast_design = None
    # Per-paradigm nav display mapping (from --config): paradigm -> {group, label}.
    paradigm_display = None
    # Analyses to omit from the gallery (from --config); CLI flag takes precedence.
    cfg_exclude = None
    # Treatment-group display names / order (from --config `groups:`).
    group_labels = group_order = None
    config_res_inputs = []

    study_cfg = config_dir = None
    if config_file is not None:
        config_path = Path(config_file).resolve()
        config_dir = config_path.parent
        with open(config_path) as f:
            study_cfg = _yaml.safe_load(f)

    try:
        profile = get_profile(profile_name or (study_cfg or {}).get("profile"))
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    own = {opt.name for opt in profile.cli_options()}
    for param in ctx.command.params:
        if (param.name in profile_cli and param.name not in own
                and ctx.get_parameter_source(param.name) is click.core.ParameterSource.COMMANDLINE):
            click.echo(f"Error: {param.opts[0]} is not an option of the {profile.name} profile.",
                       err=True)
            sys.exit(1)

    # Parse paired inputs with labels. Labels are assigned in order to the
    # profile's input options, then to --results.
    all_inputs = []
    for kind in profile.input_options():
        for path in profile_cli.get(kind) or ():
            all_inputs.append((kind, path))
    for path in results_dirs:
        all_inputs.append(("results", path))

    # Pad labels with auto-generated ones if needed
    padded_labels = list(labels)
    for i in range(len(padded_labels), len(all_inputs)):
        padded_labels.append(Path(all_inputs[i][1]).name)

    paired: dict[str, list[SourceInput]] = {kind: [] for kind in profile.input_options()}
    res_inputs = []
    for (kind, path), lbl in zip(all_inputs, padded_labels):
        si = SourceInput(path=path, label=lbl)
        if kind == "results":
            res_inputs.append(si)
        else:
            paired[kind].append(si)
    cli_values = {**profile_cli, **paired}

    def _warn(message):
        click.echo(message, err=True)

    # If --config provided, read paths from unified study.yaml
    if study_cfg is not None:
        paths = study_cfg.get("paths", {})

        def _resolve(p: str, default: str) -> str:
            return resolve_config_path(p, default, config_dir)

        def _labelled(spec, scalar_default, scalar_label, explicit, sub=None):
            return labelled_inputs(spec, scalar_default, scalar_label, explicit,
                                   resolve=_resolve, sub=sub)

        study_contrasts = normalize_study_contrasts(study_cfg)
        options = profile.read_options(cli_values, study_cfg, config_dir, _resolve,
                                       study_contrasts, _warn, _labelled)

        # Results trees, each a list of {path, label} (compared sources) or scalar.
        sub = profile.results_subdir(study_cfg)
        config_res_inputs.extend(
            _labelled(paths.get("results"), "./results", None,
                      paths.get("results") is not None, sub=sub)
        )

        # Merge: CLI flags take precedence over config
        if title is None:
            title = (study_cfg.get("gallery_title")
                     or study_cfg.get("name", profile.default_title))
        if output is None:
            output = _resolve(paths.get("gallery"), "./gallery")

        # Study contrasts drive which per-contrast figures get rendered.
        if not contrasts:
            contrasts = [c["name"] for c in study_contrasts] or None
        if contrast_labels is None:
            contrast_labels = {c["name"]: c["label"] for c in study_contrasts if c.get("label")} or None
        if contrast_groups is None:
            contrast_groups = {c["name"]: c["group"] for c in study_contrasts if c.get("group")} or None
        if contrast_meta is None:
            contrast_meta = {
                c["name"]: {
                    "role": c.get("role", "exploratory"),
                    "test": c.get("test", "difference"),
                    "gate_on": ([c["gate_on"]] if isinstance(c.get("gate_on"), str)
                                else list(c.get("gate_on") or [])),
                }
                for c in study_contrasts
                # Only emit for contrasts that declare hypothesis-testing intent.
                if c.get("role") or c.get("test") or c.get("gate_on")
            } or None
        contrast_design = {
            c["name"]: {"group_a": c["group_a"], "group_b": c["group_b"]}
            for c in study_contrasts if c.get("group_a") and c.get("group_b")
        } or None
        # Per-paradigm nav display, co-located under each paradigm's `display:` key.
        if paradigm_display is None:
            paradigm_display = {
                name: p["display"]
                for name, p in (study_cfg.get("paradigms") or {}).items()
                if isinstance(p, dict) and p.get("display")
            } or None
        cfg_exclude = study_cfg.get("exclude_analyses")
        group_labels, group_order = study_group_display(study_cfg)
    else:
        options = profile.read_options(cli_values, None, None, None, [], _warn, None)

    if title is None:
        title = profile.default_title
    if output is None:
        click.echo("Error: --output is required (or provide --config with paths.gallery).", err=True)
        sys.exit(1)

    # Fall back to config-provided labeled inputs when none given on the CLI.
    if not res_inputs and config_res_inputs:
        res_inputs = config_res_inputs

    config = BuildConfig(
        output_dir=output,
        title=title,
        results=res_inputs,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        thumb_workers=thumb_workers,
        render_figures=render_figures,
        figure_dpi=figure_dpi,
        contrasts=contrasts,
        contrast_labels=contrast_labels,
        contrast_groups=contrast_groups,
        contrast_meta=contrast_meta,
        contrast_design=contrast_design,
        paradigm_display=paradigm_display,
        group_labels=group_labels,
        group_order=group_order,
        home_link=home_link,
        home_label=home_label,
        # CLI flag > study-config `exclude_analyses:` > the profile's default.
        exclude_analyses=(list(exclude_analyses) if exclude_analyses
                          else list(cfg_exclude) if cfg_exclude is not None
                          else None),
        profile=profile.name,
        options=options,
    )

    from .builder import build as do_build

    do_build(config, verbose=verbose)

    if serve_after:
        _serve_gallery(Path(output), port)


# Each installed profile's own build options (e.g. its inputs and helpers).
build.params.extend(_profile_options())


def _serve_gallery(gallery: Path, port: int) -> None:
    """Serve a built gallery directory over HTTP until interrupted."""
    if not (gallery / "index.html").exists():
        click.echo(f"Error: {gallery} does not contain index.html. Run 'build' first.", err=True)
        sys.exit(1)

    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(gallery))

    class _Server(socketserver.TCPServer):
        # Reuse the address so re-hosting right after a previous serve doesn't hit
        # "address already in use" while the old socket lingers in TIME_WAIT.
        allow_reuse_address = True

    click.echo(f"Serving gallery at http://localhost:{port}")
    click.echo("Press Ctrl+C to stop.")
    with _Server(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\nStopped.")


@main.command()
@click.argument("gallery_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--port", "-p", default=5500, type=int, help="Port to serve on.")
def serve(gallery_dir, port):
    """Serve a built gallery locally for preview."""
    _serve_gallery(Path(gallery_dir), port)


@main.command()
@click.argument("gallery_dir", type=click.Path(exists=True, file_okay=False))
def info(gallery_dir):
    """Print stats about a built gallery."""
    gallery = Path(gallery_dir)
    manifest_path = gallery / "data" / "manifest.json"
    if not manifest_path.exists():
        click.echo(f"Error: No manifest.json found in {gallery}/data/", err=True)
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text())
    stats = manifest.get("stats", {})

    click.echo(f"Gallery: {manifest.get('title', 'Unknown')}")
    click.echo(f"Location: {gallery.resolve()}")
    click.echo(f"Sources: {', '.join(manifest.get('sources', []))}")
    click.echo(f"Paradigms: {stats.get('paradigm_count', 0)}")
    click.echo(f"Figures: {stats.get('total_figures', 0)}")
    click.echo(f"Tables: {stats.get('total_tables', 0)}")
    click.echo(f"Digests: {stats.get('total_summaries', 0)}")

    # List paradigms and analyses
    for paradigm, analyses in manifest.get("paradigms", {}).items():
        click.echo(f"\n  {paradigm}:")
        for analysis, data in analyses.items():
            n_figs = sum(len(v) for v in data.get("figures", {}).values())
            n_tbls = sum(len(v) for v in data.get("tables", {}).values())
            has_summary = "+" if data.get("summary") else "-"
            click.echo(f"    {analysis}: {n_figs} figs, {n_tbls} tables, summary={has_summary}")
