"""Derive the golden-build fixtures from two real results trees.

Run once, by hand, on a machine that has the source trees; the tests only read
what it writes. Kept so that what the fixtures are, and how they were cut, is a
matter of record rather than memory:

    uv run python tests/fixtures/make_fixtures.py

- ``eeg/`` — the FORGE treatment study's source-analytics results tree
  (analyses-v2, source-analytics v0.7.1) and its localization derivatives.
- ``mri_h1c/`` — the cuprizone H1c export that the source-lightbox feasibility
  test built (NEURO_LIGHTBOX_PLAN.md §2), in source-lightbox's results layout.
- ``eeg_legacy/`` — older output shapes neither tree has (retired vertex modules,
  legacy column names, two compared results trees), written from nothing.

Both studies are unpublished and this repository is public, so the fixtures keep
the trees' *structure* — folder layout, file names, column names, contrast /
band / ROI / group names, which rows exist — and replace every measured number
with a synthetic one. Rows are chosen before any value is synthesised, so the
choice does not depend on the real results. The synthetic values are internally
coherent (an effect, its statistic and its p move together; CIs bracket their
estimate; ``significant`` agrees with the p it is read from) so that every
digest and renderer path sees both significant and null rows.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import math
import random
import shutil
import statistics
import subprocess
from pathlib import Path

import yaml
from PIL import Image

HERE = Path(__file__).resolve().parent
FORGE = Path("/mnt/carceri/research/EEG/FORGE/treatment")
H1C = Path("/mnt/arborea/cuprizone/scratch/lightbox_h1c")
SOURCE_ANALYTICS = Path.home() / "sandbox" / "source-analytics"
SA_RELEASE = "v0.8.2"   # the release whose analysis metadata the fake interpreter serves

# Six ROIs and six channels: enough units for the per-ROI digests (3–40) and a
# small enough tree to commit.
KEEP_ROIS = ("Motor_L", "Motor_R", "Auditory_L", "Auditory_R", "Thalamus", "Hippocampus_Ant_L")
KEEP_CHANNELS = ("E3", "E7", "E12", "E18", "E24", "E29")
ROW_CAP = 60
# One table stays over the gallery's 500-row display cap, so the truncation path
# ("showing 500 of N", the full CSV linked) is part of the golden build.
ROW_CAP_OVERRIDE = {"roi_based/roi_psd/roi_psd_posthoc_roi.csv": 540}

EEG_TABLES = {
    "roi_based": ["roi_psd", "roi_aperiodic", "roi_cross_freq", "roi_directed",
                  "roi_graph", "roi_nbs", "roi_signature"],
    "shell_mc": ["roi_psd"],
    "cartesian_mc": ["electrode_psd", "electrode_aperiodic", "electrode_comparison",
                     "electrode_connectivity", "electrode_signature"],
}

_DEGENERATE = {"", "na", "nan", "none"}
_TRUE = {"TRUE", "True", "true"}
_BOOL = _TRUE | {"FALSE", "False", "false"}


# --------------------------------------------------------------------------- #
# Synthetic values
# --------------------------------------------------------------------------- #
def _rng(*parts) -> random.Random:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _fmt(v: float) -> str:
    return f"{v:.6g}"


_Q_NAMES = {"q_value", "q", "group_q", "interaction_q", "p_fdr", "q_fdr", "p_corrected",
            "component_p", "cluster_p"}


def _is_p(name: str) -> bool:
    n = name.lower()
    return (n in _Q_NAMES or n in ("p", "p_value") or "p_value" in n
            or n.endswith("_p") or n.startswith("p_"))


def _ci_side(name: str) -> str | None:
    n = name.lower()
    if any(t in n for t in ("lcl", "ci_lo", "ci_lower")) or n.endswith("_low"):
        return "lo"
    if any(t in n for t in ("ucl", "ci_hi", "ci_upper")) or n.endswith("_high"):
        return "hi"
    return None


def _ci_base(name: str, headers: list[str]) -> str | None:
    n = name
    cands: list[str] = []
    for tok in ("_lcl", "_ucl", "_ci_lo", "_ci_hi", "_low", "_high"):
        if n.endswith(tok):
            stem = n[: -len(tok)]
            # region_ci_lo brackets region_hedges_g, not the region's name
            cands += [f"{stem}_hedges_g", stem]
    if "ci_lower" in n or "ci_upper" in n:
        cands.append(n.replace("ci_lower", "accuracy").replace("ci_upper", "accuracy"))
    if n.startswith("ci95"):
        cands.append("estimate")
    return next((c for c in cands if c in headers), None)


def _bounded(name: str) -> bool:
    n = name.lower()
    return (any(t in n for t in ("accuracy", "auc", "sensitivity", "specificity"))
            and not n.endswith("_gain")) or n.startswith("frac_")


# Whole numbers that are results (the size and place of what was found), unlike
# the design counts (n per group, n ROIs, permutations) and ids that are kept.
_RESULT_COUNTS = {"n_edges", "n_edges_increase", "n_edges_decrease", "n_vertices",
                  "n_equivalent", "n_nominal_sig", "peak_vertex"}
# Flags that are results, recomputed from the synthetic row rather than kept.
_RESULT_FLAGS = {"equivalent", "exceeds_electrode"}


def _kinds(headers: list[str], rows: list[dict]) -> dict[str, str]:
    """How each column is synthesised. Anything not a measured result is kept."""
    kinds = {}
    for col in headers:
        vals = [r[col] for r in rows if str(r.get(col, "")).strip().lower() not in _DEGENERATE]
        low = col.lower()
        if vals and set(vals) <= _BOOL:
            kinds[col] = ("sigflag" if (low == "significant" or low.endswith("_significant"))
                          else "resultflag" if low in _RESULT_FLAGS else "keep")
            continue
        if low == "sig_label":
            kinds[col] = "siglabel"
            continue
        if low in _RESULT_COUNTS and vals:
            kinds[col] = "count"
            continue
        nums = [_float(v) for v in vals]
        if _bounded(col) and vals and all(n is not None for n in nums):
            kinds[col] = "bounded"
        elif not vals or any(n is None for n in nums) or len(set(vals)) <= 1:
            kinds[col] = "keep"
        elif all(float(n).is_integer() for n in nums):
            kinds[col] = "keep"          # design counts and ids: n per group, component, node
        elif _is_p(col):
            kinds[col] = "q" if low in _Q_NAMES else "p"
        elif _ci_side(col) and _ci_base(col, headers):
            kinds[col] = "ci_" + _ci_side(col)
        elif _bounded(col):
            kinds[col] = "bounded"
        elif "correlation_r" in low or (low.startswith("corr_") and low.endswith("_r")):
            kinds[col] = "corr"
        elif any(n < 0 for n in nums):
            kinds[col] = "signed"
        else:
            kinds[col] = "positive"
    return kinds


def synthesise(headers: list[str], rows: list[dict], key: str) -> list[dict]:
    """Replace every measured number in ``rows`` with a coherent synthetic one."""
    kinds = _kinds(headers, rows)
    scale = {}
    for col, kind in kinds.items():
        if kind in ("signed", "positive"):
            nums = [abs(_float(r[col])) for r in rows if _float(r.get(col)) is not None]
            centre = statistics.median(nums) if nums else 1.0
            scale[col] = centre or (max(nums) if nums else 1.0) or 1.0

    out = []
    for i, row in enumerate(rows):
        rng = _rng(key, i)
        z = rng.gauss(0.0, 1.6)                       # the row's latent effect
        new = dict(row)

        def present(col):
            return str(row.get(col, "")).strip().lower() not in _DEGENERATE

        for col in headers:                            # effects, stats, descriptives
            if not present(col):
                continue
            kind = kinds[col]
            if kind == "signed":
                new[col] = _fmt(scale[col] * (z / 1.6 + 0.25 * rng.gauss(0, 1)))
            elif kind == "positive":
                new[col] = _fmt(scale[col] * math.exp(0.3 * rng.gauss(0, 1)))
            elif kind == "bounded" and col.lower().startswith("frac_"):
                new[col] = _fmt(0.5 * rng.random())
            elif kind == "bounded":
                new[col] = _fmt(min(0.99, max(0.02, 0.5 + 0.12 * z + 0.04 * rng.gauss(0, 1))))
            elif kind == "count":
                new[col] = str(max(1, round(8 * math.exp(0.6 * rng.gauss(0, 1)))))
            elif kind == "corr":
                new[col] = _fmt(min(0.95, max(-0.95, 0.45 + 0.3 * rng.gauss(0, 1))))
        _split_edges(new, row, headers, rng)
        for col in headers:                            # p / q from the latent effect
            if not present(col) or kinds[col] not in ("p", "q"):
                continue
            p = 2.0 * (1.0 - _phi(abs(z + 0.3 * rng.gauss(0, 1))))
            if kinds[col] == "q":
                p *= 2.5
            new[col] = _fmt(min(1.0, max(1e-5, p)))
        for col in headers:                            # CIs bracket their estimate
            if not present(col) or not kinds[col].startswith("ci_"):
                continue
            base_col = _ci_base(col, headers)
            base = _float(new.get(base_col))
            if base is None:
                continue
            width = abs(base) * 0.6 + 0.05
            new[col] = _fmt(base - width if kinds[col] == "ci_lo" else base + width)

        sig_p = _sig_p(new, headers)
        for col in headers:                            # flags agree with their p
            if not present(col):
                continue
            if kinds[col] == "sigflag":
                src = {"group_significant": "group_q",
                       "interaction_significant": "interaction_q"}.get(col.lower())
                p = _float(new.get(src)) if src else sig_p
                new[col] = _word(rows, col, p is not None and p < 0.05)
            elif kinds[col] == "resultflag" and col.lower() == "equivalent":
                new[col] = _word(rows, col, abs(z) < 0.6)    # small effect: equivalent
            elif kinds[col] == "resultflag":                  # exceeds_electrode
                a = _float(new.get("region_hedges_g"))
                b = _float(new.get("electrode_hedges_g"))
                new[col] = _word(rows, col, a is not None and b is not None and abs(a) > abs(b))
            elif kinds[col] == "siglabel":
                new[col] = ("" if sig_p is None or sig_p >= 0.05 else
                            "***" if sig_p < 0.001 else "**" if sig_p < 0.01 else "*")
        out.append(new)
    return out


def _word(rows: list[dict], col: str, yes: bool) -> str:
    """TRUE / FALSE in the spelling the column already uses."""
    true_word = next((v for v in (r[col] for r in rows) if v in _TRUE), "TRUE")
    false_word = {"TRUE": "FALSE", "True": "False", "true": "false"}[true_word]
    return true_word if yes else false_word


def _split_edges(new: dict, row: dict, headers: list[str], rng: random.Random) -> None:
    """NBS rows: the increase and decrease edges add up to the component, and the
    direction says which (mixed when both)."""
    if not {"n_edges", "n_edges_increase", "n_edges_decrease"} <= set(headers):
        return
    n = _float(new.get("n_edges"))
    if n is None or _float(row.get("n_edges_increase")) is None:
        return
    inc = rng.randint(0, int(n))
    new["n_edges_increase"], new["n_edges_decrease"] = str(inc), str(int(n) - inc)
    if "direction" in headers and str(row.get("direction", "")).strip().lower() not in _DEGENERATE:
        new["direction"] = ("increase" if inc == n else "decrease" if inc == 0 else "mixed")


def _sig_p(rec: dict, headers: list[str]):
    for col in ("q_value", "p_fdr", "q_fdr", "p_corrected", "component_p", "cluster_p",
                "p_value", "p"):
        if col in headers and _float(rec.get(col)) is not None:
            return _float(rec[col])
    return None


# --------------------------------------------------------------------------- #
# Row selection
# --------------------------------------------------------------------------- #
def _units(value: str) -> list[str]:
    return [v.strip() for v in str(value).split("->")]


def _keep_row(rec: dict, universe: set[str], keep: set[str]) -> bool:
    for col in ("spatial", "roi", "channel", "source", "target", "roi_i", "roi_j"):
        for unit in _units(rec.get(col, "")):
            if unit in universe and unit not in keep:
                return False
    return True


def _cap(rows: list[dict], headers: list[str], cap: int) -> list[dict]:
    """At most ``cap`` rows, taken round-robin across contrasts in file order, so
    every contrast keeps rows."""
    if len(rows) <= cap:
        return rows
    key = next((k for k in ("hypothesis", "contrast", "key") if k in headers), None)
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(r.get(key, "") if key else "", []).append(i)
    picked: list[int] = []
    depth = 0
    while len(picked) < cap:
        for idxs in groups.values():
            if depth < len(idxs) and len(picked) < cap:
                picked.append(idxs[depth])
        depth += 1
    return [rows[i] for i in sorted(picked)]


def _read(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def _write(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _png(path: Path, seed: str) -> None:
    rng = _rng("png", seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (24, 16), tuple(rng.randrange(40, 220) for _ in range(3))).save(path)


# --------------------------------------------------------------------------- #
# EEG: FORGE treatment
# --------------------------------------------------------------------------- #
def _forge_study() -> dict:
    with open(FORGE / "study_treatment_mc.yaml") as f:
        return yaml.safe_load(f)


def make_eeg(out: Path) -> None:
    study = _forge_study()
    universe = {r for rois in study["roi_categories"].values() for r in rois}
    universe |= {f"E{i}" for i in range(1, 31)}
    keep = set(KEEP_ROIS) | set(KEEP_CHANNELS)

    tables = FORGE / "analyses" / "results" / "tables"
    res = out / "results" / "tables"
    for paradigm, analyses in EEG_TABLES.items():
        for analysis in analyses:
            for src in sorted((tables / paradigm / analysis).glob("*.csv")):
                rel = f"{paradigm}/{analysis}/{src.name}"
                headers, rows = _read(src)
                rows = [r for r in rows if _keep_row(r, universe, keep)]
                rows = _cap(rows, headers, ROW_CAP_OVERRIDE.get(rel, ROW_CAP))
                _write(res / paradigm / analysis / src.name, headers,
                       synthesise(headers, rows, rel))

    # roi_connectivity is descriptive: an empty tables folder, and figures whose
    # names the digest parses (circos_<metric>_<band>, heatmap_<metric>_<band>).
    (res / "roi_based" / "roi_connectivity").mkdir(parents=True, exist_ok=True)

    # A retired analysis an old tree still carries, and the combined alias the
    # study excludes: neither may reach the gallery.
    _write(res / "roi_based" / "vertex_specparam" / "vertex_specparam_stats.csv",
           ["contrast", "band", "vertex_idx", "hedges_g", "p_fdr"],
           [{"contrast": "disease_effect", "band": "Alpha", "vertex_idx": str(i),
             "hedges_g": _fmt(0.1 * i), "p_fdr": "0.5"} for i in range(3)])
    _write(res / "roi_based" / "roi_network" / "roi_network_stats.csv",
           ["contrast", "band", "roi", "hedges_g", "p_fdr"],
           [{"contrast": "disease_effect", "band": "Alpha", "roi": "Motor_L",
             "hedges_g": "0.4", "p_fdr": "0.2"}])

    figs = out / "results" / "figures"
    for rel in (
        "roi_based/roi_connectivity/circos_aec_alpha.png",
        "roi_based/roi_connectivity/circos_imag_coherence_low_gamma.png",
        "roi_based/roi_connectivity/heatmap_dwpli_beta.png",
        "roi_based/roi_connectivity/heatmap_imag_coherence_low_gamma.png",
        "roi_based/roi_psd/effect_size_disease_effect_Low_Gamma_relative.png",
        "roi_based/roi_psd/band_by_region_Low Gamma_absolute.png",
        "roi_based/roi_psd/diagnostics/residuals_qq.png",     # nested: flattened to a__b.png
        "roi_based/roi_directed/roi_directed_global_bar.png",
        "roi_based/vertex_specparam/vertex_specparam_map.png",
        "cartesian_mc/electrode_psd/electrode_topomap_disease_effect_Alpha.png",
    ):
        _png(figs / rel, rel)

    # Provenance (source-analytics v0.8.2+): a fixed-placement run, a Monte Carlo
    # run with parcel caveats and a plugin that did not provide the analysis, and
    # (electrode_psd, the rest) older output with none.
    _provenance(res / "roi_based" / "roi_psd", "roi_psd", "roi_based",
                description="ellipsoid_roi_based, allen26, fixed placement",
                atlas="allen26", sampling="fixed")
    _provenance(res / "shell_mc" / "roi_psd", "roi_psd", "shell_mc",
                description="ellipsoid_shell, allen26, Monte Carlo (K=100)",
                atlas="allen26", sampling="monte_carlo",
                plugins={"vertex": {"version": "0.1.0"}},
                caveats={"Thalamus": "sampled in 31% of draws",
                         "Hippocampus_Ant_L": "not separable from Hippocampus_Ant_R"})

    # The analytics working tree: only the edge CSV the circos average from.
    edges = out / "analytics" / "roi_based" / "roi_connectivity" / "data"
    _write(edges / "roi_connectivity_edges.csv",
           ["subject", "group", "band", "roi1", "roi2", "imag_coherence", "aec"],
           [{"subject": "sub-901", "group": "KO_VEH", "band": "Alpha", "roi1": "Motor_L",
             "roi2": "Motor_R", "imag_coherence": "0.1", "aec": "0.2"}])

    _make_localizations(out / "localization", study)
    _write_eeg_study(out, study)
    _write_analysis_meta(out / "analysis_meta.json")


def _provenance(tbl_dir: Path, analysis: str, paradigm: str, *, description: str,
                atlas: str, sampling: str, plugins: dict | None = None,
                caveats: dict | None = None) -> None:
    record = {
        "schema": 1,
        "written": "2026-09-18T14:01:36-04:00",
        "analysis": analysis,
        "paradigm": paradigm,
        "profile": None,
        "study_config": "study.yaml",
        "source_analytics": {"version": "0.8.2", "git_describe": "v0.8.2"},
        "steps": ["aggregate", "process", "setup"],
        "subjects": {"n": 6, "groups": {"KO_HD_ICV": 2, "KO_VEH": 2, "WT_VEH": 2},
                     "ids": [f"sub-90{i}" for i in range(1, 7)]},
        "localization": {
            "n_with_manifest": 6, "n_unrecorded": 0, "description": description,
            "version": "0.5.1", "preset": "ellipsoid_cartesian", "atlas": atlas,
            "bem_type": "ellipsoid", "source_type": "volume", "surface_method": None,
            "spacing_mm": None, "source_sampling": sampling, "inverse_method": "sLORETA",
            "orientation": "fixed",
        },
    }
    if plugins:
        record["plugins"] = plugins
    if caveats:
        record["parcel_caveats"] = caveats
    (tbl_dir / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")


_SUBJECTS = {"901": "WT_VEH", "902": "WT_VEH", "903": "KO_VEH", "904": "KO_VEH",
             "905": "KO_HD_ICV", "906": "KO_HD_ICV"}
_QC_ONLY = {"907": "KO_HD_IV", "908": "KO_LD_IV_ICV"}   # in the QC table, no folder


def _snapshot(source_type: str, sampling: str | None) -> dict:
    src = {"source_sampling": sampling, "monte_carlo": {"n_draws": 100}} if sampling else {}
    return {
        "source_localization_version": "0.5.1",
        "config": {
            "pipeline": {"bem_type": "ellipsoid", "source_type": source_type},
            "source_space": src,
            "inverse": {"method": "sLORETA", "orientation": "fixed"},
            "provenance": {"preset": f"ellipsoid_{source_type}", "atlas": "allen26"},
        },
    }


def _make_localizations(root: Path, study: dict) -> None:
    steps = ("step1_electrodes", "step3_source_space", "step4_forward",
             "step5_inverse_signed", "step6_roi_extraction_signed")
    for name, source_type, sampling, unrecorded in (
        ("rest_roi_allen26", "roi_based", None, {"906"}),
        ("rest_shell_mc", "shell", "monte_carlo", set()),
    ):
        base = root / name
        for sid in _SUBJECTS:
            pipe = base / "derivatives" / f"sub-{sid}" / "pipeline"
            for step in steps:
                _png(pipe / "figures" / f"{step}.png", f"{name}/{sid}/{step}")
            if sid not in unrecorded:
                (pipe / "data").mkdir(parents=True, exist_ok=True)
                (pipe / "data" / "config_resolved.yaml").write_text(
                    yaml.safe_dump(_snapshot(source_type, sampling), sort_keys=False))
        qc = base / "qc"
        _qc_metrics(qc / "qc_metrics.csv", name)
        if name == "rest_roi_allen26":
            for fig in ("01_source_amplitude", "02_forward_condition", "03_timepoints",
                        "04_sources_per_roi"):
                _png(qc / "figures" / f"{fig}.png", f"{name}/qc/{fig}")
            (qc / "qc_report.html").write_text(
                "<!DOCTYPE html><html><body><h1>QC report (fixture)</h1></body></html>\n")


def _qc_metrics(path: Path, seed: str) -> None:
    src = FORGE / "preprocessing" / "derivatives" / "rest_roi_allen26" / "qc" / "qc_metrics.csv"
    headers, _ = _read(src)
    rows = []
    for sid, group in {**_SUBJECTS, **_QC_ONLY}.items():
        rng = _rng("qc", seed, sid)
        rec = {h: "" for h in headers}
        rec.update(subject_id=sid, group=group, n_channels="30", sfreq="1000.0",
                   n_sources="201", stc_n_sources="201", n_rois="26", outlier_flag="False")
        rec["forward_condition_number"] = _fmt(70.0 + rng.gauss(0, 1) + (60 if sid == "903" else 0))
        rec["stc_n_times"] = str(300000 + rng.randrange(0, 90000))
        for col in ("stc_amp_mean", "stc_amp_max", "stc_amp_std", "roi_amp_mean"):
            rec[col] = _fmt(1.4e-9 * math.exp(0.2 * rng.gauss(0, 1)))
        rec["processing_time_sec"] = _fmt(40 + 5 * rng.random())
        rows.append(rec)
    _write(path, headers, rows)


def _write_eeg_study(out: Path, study: dict) -> None:
    kept = {k: study[k] for k in ("name", "gallery_title", "exclude_analyses", "groups",
                                  "group_order", "hypotheses", "circos_metrics",
                                  "roi_categories")}
    kept["pipeline"] = {"atlas": study["pipeline"]["atlas"]}
    kept["paths"] = {
        "results": "./results",
        "analytics": "./analytics",
        "gallery": "./gallery",
        "localizations": [
            {"path": "./localization/rest_roi_allen26", "label": "ROI-based (Allen26)"},
            {"path": "./localization/rest_shell_mc", "label": "MC Shell"},
        ],
        # A stand-in for the source-analytics interpreter (see sa_python).
        "source_analytics_python": "./sa_python",
    }
    kept["paradigms"] = {p: {"display": study["paradigms"][p]["display"]}
                         for p in ("roi_based", "shell_mc", "cartesian_mc")}
    header = ("# Golden-build fixture, cut from the FORGE treatment study config by\n"
              "# tests/fixtures/make_fixtures.py. Only the keys the gallery reads.\n")
    (out / "study.yaml").write_text(
        header + yaml.safe_dump(kept, sort_keys=False, allow_unicode=True))


def _write_analysis_meta(path: Path) -> None:
    """source-analytics' ``analysis_meta()`` as of SA_RELEASE, read from git."""
    src = subprocess.run(
        ["git", "-C", str(SOURCE_ANALYTICS), "show",
         f"{SA_RELEASE}:src/source_analytics/core.py"],
        capture_output=True, text=True, check=True).stdout
    for node in ast.parse(src).body:
        target = (node.target if isinstance(node, ast.AnnAssign)
                  else node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == "ANALYSIS_METADATA":
            meta = ast.literal_eval(node.value)
            break
    else:
        raise SystemExit("ANALYSIS_METADATA not found")
    path.write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n")


# --------------------------------------------------------------------------- #
# EEG, legacy: written here from nothing (no study data)
# --------------------------------------------------------------------------- #
# Output an older or wider tree still carries and FORGE's analyses-v2 does not:
# the retired vertex modules (published with include_retired), tables in the
# legacy column names (contrast / roi / power_type / hedges_g / p_fdr), a
# plugin's provenance, and two results trees compared side by side.
_LEGACY_CONTRASTS = ("disease_effect", "hd_icv_rescue")
_LEGACY_BANDS = ("Alpha", "Low Gamma")


def make_eeg_legacy(out: Path) -> None:
    for label, sub in (("Shell", "results_shell"), ("Cartesian", "results_cartesian")):
        tables = out / sub / "tables" / "resting"
        rows = [{"contrast": c, "band": b, "metric": "relative", "cluster_id": str(k),
                 "n_vertices": str(40 + 10 * k), "peak_t": _fmt(t), "cluster_stat": _fmt(8 * t),
                 "p_corrected": _fmt(p)}
                for c, b, k, t, p in _legacy_rows(f"{sub}/cluster", "cluster")]
        _write(tables / "vertex_cluster" / "cluster_results.csv", list(rows[0]), rows)
        if label == "Shell":   # without it, Cartesian's overview is the cluster heatmap
            rows = [{"contrast": c, "band": b, "metric": "relative",
                     "max_abs_hedges_g": _fmt(abs(t) / 2), "n_nominal_sig": str(k * 7),
                     "n_vertices": "1200"}
                    for c, b, k, t, _ in _legacy_rows(f"{sub}/summary", "summary")]
            _write(tables / "vertex_cluster" / "effect_size_summary.csv", list(rows[0]), rows)
        rows = [{"contrast": c, "band": b, "vertex_idx": str(v), "hedges_g": _fmt(t / 3),
                 "t": _fmt(t), "p": _fmt(p), "p_fdr": _fmt(min(1.0, 3 * p))}
                for c, b, v, t, p in _legacy_rows(f"{sub}/voxel", "voxel")]
        _write(tables / "vertex_cluster" / "voxelwise_stats.csv", list(rows[0]), rows)
        _provenance(tables / "vertex_cluster", "vertex_cluster", "resting",
                    description="ellipsoid_shell, allen26, fixed placement",
                    atlas="allen26", sampling="fixed",
                    plugins={"vertex": {"version": "0.1.0", "provides_this_analysis": True},
                             "other": {"version": "2.0"}})
        _png(out / sub / "figures" / "resting" / "vertex_cluster" / "cluster_map_disease_effect.png",
             f"{sub}/cluster_map")

    tables = out / "results_shell" / "tables" / "resting"
    rows = []
    for c, b, k, t, p in _legacy_rows("graph", "graph"):
        for gm in ("global_efficiency", "modularity", "small_worldness"):
            rows.append({"contrast": c, "band": b, "conn_metric": "imag_coherence",
                         "graph_metric": gm, "roi": "", "hedges_g": _fmt(t / 2 + 0.1 * k),
                         "effect_size_type": "hedges_g", "t": _fmt(t), "p": _fmt(p),
                         "p_fdr": _fmt(min(1.0, 2 * p)),
                         "significant": "TRUE" if 2 * p < 0.05 else "FALSE"})
    _write(tables / "vertex_graph" / "vertex_graph_stats.csv", list(rows[0]), rows)

    rows = []
    for c, b, k, t, p in _legacy_rows("fcd", "fcd"):
        rec = {"contrast": c, "band": b, "metric": "fcd", "corr_mean_r": _fmt(0.3 + 0.1 * k),
               "corr_cv_r": _fmt(0.2 + 0.05 * k)}
        for lvl, g in (("source_mean", t / 2), ("sensor_mean", t / 3),
                       ("source_cv", -t / 4), ("sensor_cv", t / 5)):
            rec.update({f"{lvl}_g": _fmt(g), f"{lvl}_ci_lo": _fmt(g - 0.5),
                        f"{lvl}_ci_hi": _fmt(g + 0.5)})
        rows.append(rec)
    _write(tables / "fcd_comparison" / "fcd_comparison_stats.csv", list(rows[0]), rows)

    # roi_psd in the legacy column names, before the native hypothesis schema.
    rows = []
    for c, b, k, t, p in _legacy_rows("roi_psd", "roi"):
        for roi in KEEP_ROIS[:4]:
            q = min(1.0, p * (1 + KEEP_ROIS.index(roi)))
            rows.append({"contrast": c, "roi": roi, "band": b, "power_type": "relative",
                         "hedges_g": _fmt(t / 2 - 0.2 * KEEP_ROIS.index(roi)), "p_fdr": _fmt(q),
                         "significant": "TRUE" if q < 0.05 else "FALSE",
                         "group_a": "KO_VEH", "group_b": "WT_VEH"})
    _write(tables / "roi_psd" / "roi_psd_posthoc_roi.csv", list(rows[0]), rows)

    study = {
        "name": "Legacy outputs (fixture)",
        "include_retired": True,
        "exclude_analyses": [],
        "groups": [{"name": "WT_VEH", "label": "WT Vehicle"},
                   {"name": "KO_VEH", "label": "KO Vehicle"},
                   {"name": "KO_HD_ICV", "label": "KO High-Dose ICV"}],
        "contrasts": [
            {"name": "disease_effect", "label": "KO vs WT", "group": "Disease effect",
             "group_a": "KO_VEH", "group_b": "WT_VEH", "role": "confirmatory"},
            {"name": "hd_icv_rescue", "label": "HD-ICV rescue", "group": "Treatment rescue",
             "group_a": "KO_HD_ICV", "group_b": "KO_VEH", "role": "exploratory",
             "gate_on": "disease_effect"},
        ],
        "paradigms": {"resting": {"display": {"group": "Resting", "label": "Legacy vertex"}}},
        "paths": {
            "results": [{"path": "./results_shell", "label": "Shell"},
                        {"path": "./results_cartesian", "label": "Cartesian"}],
            "gallery": "./gallery",
        },
    }
    header = ("# Golden-build fixture: legacy and retired output shapes, written by\n"
              "# tests/fixtures/make_fixtures.py from nothing (no study data).\n")
    (out / "study.yaml").write_text(header + yaml.safe_dump(study, sort_keys=False))


def _legacy_rows(seed: str, kind: str):
    """(contrast, band, k, t, p) per contrast x band, half of them significant."""
    for i, (c, b) in enumerate((c, b) for c in _LEGACY_CONTRASTS for b in _LEGACY_BANDS):
        rng = _rng("legacy", seed, kind, i)
        t = (3.2 if i % 2 == 0 else 0.8) * (1 if rng.random() < 0.6 else -1)
        p = 2.0 * (1.0 - _phi(abs(t)))
        yield c, b, i + 1, t + 0.1 * rng.gauss(0, 1), p


# --------------------------------------------------------------------------- #
# MRI: cuprizone H1c, as exported for the feasibility test
# --------------------------------------------------------------------------- #
# export_h1c.py's mapping onto source-lightbox's native columns (plan §2): these
# columns are copies of study columns, so they are re-derived, not synthesised.
_H1C_NATIVE = {"effect_size": "d", "stat": "t", "p_value": "p"}


def make_mri(out: Path) -> None:
    src = H1C / "results" / "tables" / "rsfmri" / "h1c_function_trajectory"
    dst = out / "results" / "tables" / "rsfmri" / "h1c_function_trajectory"

    headers, rows = _read(src / "h1c_effect_size_summary.csv")
    _write(dst / "h1c_effect_size_summary.csv", headers,
           _h1c_native(synthesise(headers, rows, "h1c_effect_size_summary")))

    headers, rows = _read(src / "h1c_posthoc_roi.csv")
    regions = sorted({r["variable"] for r in rows})
    per_region = len(rows) / len(regions)
    n_keep = math.ceil(560 / per_region)
    keep = set(regions[:: max(1, len(regions) // n_keep)][:n_keep])
    rows = [r for r in rows if r["variable"] in keep]
    _write(dst / "h1c_posthoc_roi.csv", headers,
           _h1c_native(synthesise(headers, rows, "h1c_posthoc_roi")))

    shutil.copy2(src / "provenance.json", dst / "provenance.json")
    with open(H1C / "study.yaml") as f:
        study = yaml.safe_load(f)
    header = ("# Golden-build fixture: the cuprizone H1c feasibility export (plan §2),\n"
              "# copied by tests/fixtures/make_fixtures.py; numbers are synthetic.\n")
    (out / "study.yaml").write_text(
        header + yaml.safe_dump(study, sort_keys=False, allow_unicode=True))
    shutil.copy2(H1C / "export_h1c.py", out / "export_h1c.py")


def _h1c_native(rows: list[dict]) -> list[dict]:
    for r in rows:
        for native, study_col in _H1C_NATIVE.items():
            if native in r:
                r[native] = r[study_col]
    return rows


def main() -> None:
    for name, make in (("eeg", make_eeg), ("eeg_legacy", make_eeg_legacy),
                       ("mri_h1c", make_mri)):
        out = HERE / name
        keep = {"sa_python", "README.md"}
        if out.exists():
            for child in out.iterdir():
                if child.name not in keep:
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
        out.mkdir(parents=True, exist_ok=True)
        make(out)
        n = sum(1 for p in out.rglob("*") if p.is_file())
        size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
        print(f"{name}: {n} files, {size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
