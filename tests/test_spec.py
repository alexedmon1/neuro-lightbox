"""Galleries from results written to the results specification (tests/fixtures/mri_spec).

The fixture's planted truth (tests/fixtures/make_mri_spec.py): in tbss/demo, MD
treated>control and MK control>treated are FWE-significant, everything else is a
null; in vbm/demo_change, increase is significant and decrease is not.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from neuro_lightbox.builder import build
from neuro_lightbox.config import BuildConfig, SourceInput
from neuro_lightbox.scanner import SpecScanner
from neuro_lightbox.spec import find_analyses, load_analysis

RESULTS = Path(__file__).parent / "fixtures" / "mri_spec" / "results"


@pytest.fixture(scope="module")
def gallery(tmp_path_factory):
    out = tmp_path_factory.mktemp("gallery")
    build(BuildConfig(output_dir=out, results=[SourceInput(RESULTS, "demo")], profile="mri"),
          verbose=False)
    return out, json.loads((out / "data" / "manifest.json").read_text())


def test_every_listed_analysis_is_found_and_read():
    folders = find_analyses(RESULTS)
    assert [f.relative_to(RESULTS).as_posix() for f in folders] == ["tbss/demo", "vbm/demo_change"]
    spec = load_analysis(folders[0])
    assert spec.measures == ["FA", "MD", "MK"]
    tests = spec.tables_with_role("tests")[0]
    assert tests.standard()["effect_size"] == "whole_d"
    assert tests.qualifier("p_value", "PKind") == "fwe"


def test_analyses_are_grouped_by_type_and_named_by_their_record(gallery):
    _out, m = gallery
    assert set(m["paradigms"]) == {"tbss", "vbm"}
    entry = m["paradigms"]["tbss"]["tbss_demo"]
    assert entry["meta"]["display_name"] == "TBSS: demo (synthetic)"
    assert m["paradigm_meta"]["tbss"]["label"] == "TBSS"
    assert entry["spec"]["role"] == "confirmatory"
    assert entry["provenance"]["generated_by"][0]["Name"] == "neurofaune"


def test_the_summary_states_the_correction_and_every_test(gallery):
    _out, m = gallery
    html = m["paradigms"]["tbss"]["tbss_demo"]["summary"]
    assert "per contrast over the TBSS skeleton" in html                 # the correction, as stated
    assert "6 tests" in html and "2 reach fwe p &lt; 0.05" in html
    assert html.count('class="spec-sig"') >= 2 and html.count('class="spec-null"') >= 4   # nulls listed
    assert "Corpus.Callosum.and.Associated.Subcortical.White.Matter.L" in html          # named location
    assert "(selected, inflated)" in html                               # cluster effects say so


def test_figures_effect_overview_and_montages_of_significant_tests_only(gallery):
    _out, m = gallery
    names = {f["filename"] for figs in m["paradigms"]["tbss"]["tbss_demo"]["figures"].values()
             for f in figs}
    assert names == {"effects_1_tests.png", "montage_md_treated_control.png",
                     "montage_mk_control_treated.png"}
    vbm = {f["filename"] for figs in m["paradigms"]["vbm"]["vbm_demo_change"]["figures"].values()
           for f in figs}
    assert vbm == {"effects_1_tests.png", "montage_gm_increase.png"}   # drawn on the mask: no background


def test_tables_travel_with_their_column_dictionaries(gallery):
    out, _m = gallery
    for name in ("tests", "clusters"):
        assert (out / "tables" / "tbss" / "tbss_demo" / f"{name}.csv").is_file()
        assert (out / "tables" / "tbss" / "tbss_demo" / f"{name}.json").is_file()


def test_a_version_this_reader_was_not_written_for_is_skipped(tmp_path):
    root = tmp_path / "results"
    shutil.copytree(RESULTS / "tbss" / "demo", root / "demo")
    rec = json.loads((root / "demo" / "analysis.json").read_text())
    rec["spec_version"] = "1.0.0"
    (root / "demo" / "analysis.json").write_text(json.dumps(rec))
    warnings = []
    scan = SpecScanner(root, "x", warn=warnings.append).scan()
    assert not scan.spec and any("not one this gallery reads" in w for w in warnings)


def test_a_table_outside_its_folder_is_not_read(tmp_path):
    root = tmp_path / "results"
    shutil.copytree(RESULTS / "tbss" / "demo", root / "demo")
    rec = json.loads((root / "demo" / "analysis.json").read_text())
    rec["tables"][1]["path"] = "../clusters.csv"
    (root / "demo" / "analysis.json").write_text(json.dumps(rec))
    warnings = []
    spec = load_analysis(root / "demo", warnings.append)
    assert [t.role for t in spec.tables] == ["tests"] and warnings


def test_p_maps_that_do_not_say_p_or_one_minus_p_are_not_thresholded(tmp_path):
    from neuro_lightbox.profiles.mri.montage import montages

    root = tmp_path / "demo"
    shutil.copytree(RESULTS / "tbss" / "demo", root)
    rec = json.loads((root / "analysis.json").read_text())
    for m in rec["maps"]:
        m.pop("values", None)
    (root / "analysis.json").write_text(json.dumps(rec))
    logs = []
    assert montages(load_analysis(root), tmp_path / "out", 72, logs.append) == []
    assert any("does not say whether it holds p or 1 - p" in x for x in logs)


def test_declared_axes_orient_the_image_not_the_header(tmp_path):
    """A voxel at index (0, 0, 5) of an LIA image is the most right, superior, anterior one."""
    import nibabel as nib
    import numpy as np

    from neuro_lightbox.profiles.mri.montage import _load

    a = np.zeros((4, 5, 6), np.float32)
    a[0, 0, 5] = 1
    path = tmp_path / "lia.nii.gz"
    nib.save(nib.Nifti1Image(a, np.eye(4)), str(path))          # the header claims RAS
    ras = _load(path, "LIA")
    assert ras.shape == (4, 6, 5)
    assert np.argwhere(ras == 1).tolist() == [[3, 5, 4]]
    assert np.argwhere(_load(path, None) == 1).tolist() == [[0, 0, 5]]   # header: as stored


def test_opposite_one_sided_contrasts_share_a_row():
    from neuro_lightbox.spec_render import _pairs

    std = {"effect_size": "d"}
    keys = [("w1", "a>b"), ("w1", "b>a"), ("w1", "other"), ("w2", "a>b")]
    cell = {("w1", "a>b", "FA"): {"d": "0.5"}, ("w1", "b>a", "FA"): {"d": "-0.5"},
            ("w1", "a>b", "MD"): {"d": "-1.25"}, ("w1", "b>a", "MD"): {"d": "1.25"},
            ("w1", "other", "FA"): {"d": "-0.5"}, ("w2", "a>b", "FA"): {"d": "-0.5"}}
    # 'other' negates a>b on FA but has no MD: not a pair. w2 is another facet.
    assert _pairs(keys, cell, ["FA", "MD"], std) == {("w1", "b>a"): ("w1", "a>b")}
    cell[("w1", "b>a", "MD")] = {"d": "1.2"}                  # not an exact negation
    assert _pairs(keys, cell, ["FA", "MD"], std) == {}


def test_subgroup_overview_draws_each_subgroup_and_survives_tiny_ones(tmp_path):
    import csv

    from neuro_lightbox.spec_render import subgroup_dots

    root = tmp_path / "demo"
    shutil.copytree(RESULTS / "tbss" / "demo", root)
    with open(root / "tests.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for k, r in enumerate(rows):
        r["d_A"], r["d_B"], r["n_B"] = str(0.1 * k), str(40.0 if k == 0 else -0.3), "2"
    with open(root / "tests.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    cols = json.loads((root / "tests.json").read_text())
    cols.update({"d_A": {"Description": "d in A", "Standard": "subgroup_effect", "EffectMeasure": "d",
                         "Subgroup": "A"},
                 "d_B": {"Description": "d in B", "Standard": "subgroup_effect", "EffectMeasure": "d",
                         "Subgroup": "B"},
                 "n_B": {"Description": "n in B", "Standard": "subgroup_n", "Subgroup": "B"}})
    (root / "tests.json").write_text(json.dumps(cols))
    spec = load_analysis(root)
    out = subgroup_dots(spec, spec.tables_with_role("tests")[0], tmp_path / "s.png", 72)
    assert out is not None and out.stat().st_size > 0             # B (n = 2, d = 40) drawn, not fatal
    plain = load_analysis(RESULTS / "tbss" / "demo")
    assert subgroup_dots(plain, plain.tables_with_role("tests")[0], tmp_path / "t.png", 72) is None


def test_study_names_label_and_order_tests():
    from neuro_lightbox.spec import StudyNames

    n = StudyNames(labels={"change_group__p60_to_p90": "Group, early", "cuprizone>control": "cpz > ctl",
                           "cross p90": "At p90"},
                   order=["cross p90", "change_group__p60_to_p90"])
    assert n.label("change_group", "p60_to_p90") == "Group, early"           # whole-test label
    assert n.label("cross p90", "cuprizone>control") == "At p90 · cpz > ctl"  # facet and contrast apart
    assert n.label("", "other") == "other"                                    # no label: own name
    keys = [("change_group", "p60_to_p90"), ("x", "y"), ("cross p90", "cuprizone>control")]
    assert sorted(keys, key=lambda k: n.rank(*k)) == [("cross p90", "cuprizone>control"),
                                                      ("change_group", "p60_to_p90"), ("x", "y")]


def test_study_links_reach_the_sidebar_relative_to_the_gallery(tmp_path):
    from click.testing import CliRunner

    from neuro_lightbox.cli import main

    qc = tmp_path / "preprocessing" / "qc" / "index.html"
    qc.parent.mkdir(parents=True)
    qc.write_text("<html></html>")
    study = tmp_path / "analyses" / "study.yaml"
    study.parent.mkdir()
    study.write_text(f"name: demo\nprofile: mri\npaths:\n  results: {RESULTS}\n  gallery: ./gallery\n"
                     "links:\n  - label: Preprocessing QC\n    path: ../preprocessing/qc/index.html\n")
    res = CliRunner().invoke(main, ["build", "--config", str(study), "--quiet"])
    assert res.exit_code == 0, res.output
    m = json.loads((tmp_path / "analyses" / "gallery" / "data" / "manifest.json").read_text())
    assert m["links"] == [{"label": "Preprocessing QC", "href": "../../preprocessing/qc/index.html"}]


# ── Sections ────────────────────────────────────────────────────────────────────

def _analysis(**record):
    from neuro_lightbox.spec import SpecAnalysis

    return SpecAnalysis(folder=Path("x"), record=record, provenance=None, tables=[])


def test_sections_are_checked():
    from neuro_lightbox.spec import normalize_sections

    assert normalize_sections(None) == []
    got = normalize_sections([{"label": "Diffusion: TBSS", "match": {"analysis_type": "tbss"}}])
    assert got[0]["key"] == "diffusion_tbss" and got[0]["match"] == {"analysis_type": ["tbss"]}
    for bad, why in [
        ([{"match": {"analysis_type": "tbss"}}], "label"),
        ([{"label": "A"}], "match"),
        ([{"label": "A", "match": {"analysis_typ": "tbss"}}], "unknown match key"),
        ([{"label": "A", "match": {"modality": "dwi"}}, {"label": "a", "match": {"modality": "func"}}],
         "repeated"),
        ([{"label": "Unsectioned", "match": {"modality": "dwi"}}], "reserved"),
        ({"label": "A"}, "list"),
    ]:
        with pytest.raises(ValueError, match=why):
            normalize_sections(bad)


def test_section_of_first_match_wins_and_unmatched_is_listed():
    from neuro_lightbox.spec import UNSECTIONED, normalize_sections, section_of

    sections = normalize_sections([
        {"label": "ReHo", "match": {"analysis_type": "voxelwise", "modality": "func", "measures": ["reho"]}},
        {"label": "fALFF", "match": {"analysis_type": "voxelwise", "modality": "func", "measures": "fALFF"}},
        {"label": "TBSS", "match": {"analysis_type": ["tbss", "fixel"], "modality": ["dwi", "msme"]}},
        {"label": "murinet", "match": {"id_prefix": "murinet/"}},
    ])
    assert section_of(_analysis(analysis_type="voxelwise", modality="func", measures=["ReHo"]), sections) == "reho"
    assert section_of(_analysis(analysis_type="voxelwise", modality="func", measures=["fALFF"]), sections) == "falff"
    # both measures: the first section that matches
    both = _analysis(analysis_type="voxelwise", modality="func", measures=["fALFF", "ReHo"])
    assert section_of(both, sections) == "reho"
    assert section_of(_analysis(analysis_type="tbss", modality="msme"), sections) == "tbss"
    assert section_of(_analysis(analysis_type="other", id="murinet/radiomics"), sections) == "murinet"
    # every condition must hold: tbss without a modality does not match
    assert section_of(_analysis(analysis_type="tbss"), sections) == UNSECTIONED
    assert section_of(_analysis(analysis_type="vbm", modality="anat"), sections) == UNSECTIONED


# ── 0.2 runs: tests of one analysis run at different times ────────────────────────

def _as_run(src: Path, dst: Path, run: dict, keep_measures=None) -> None:
    """The fixture's tbss/demo as one 0.2 run (optionally keeping only some measures' rows)."""
    shutil.copytree(src, dst)
    a = json.loads((dst / "analysis.json").read_text())
    a.update(spec_version="0.2.0", id="dwi/tbss/demo", modality="dwi", run=run)
    if keep_measures:
        import csv

        for t in a["tables"]:
            if t.get("role") != "tests":
                continue
            p = dst / t["path"]
            with open(p, newline="") as fh:
                rows = list(csv.DictReader(fh))
            cols = list(rows[0])
            meas = next(c for c, m in json.loads(p.with_suffix(".json").read_text()).items()
                        if m.get("Standard") == "measure")
            rows = [r for r in rows if r[meas] in keep_measures]
            with open(p, "w", newline="") as fh:
                w = csv.DictWriter(fh, cols)
                w.writeheader()
                w.writerows(rows)
            t["n_rows"] = len(rows)
    (dst / "analysis.json").write_text(json.dumps(a))


@pytest.fixture
def two_runs(tmp_path):
    src = RESULTS / "tbss" / "demo"
    root = tmp_path / "results"
    _as_run(src, root / "dwi" / "tbss" / "demo" / "2026-10-05", {"id": "2026-10-05", "label": "registered"})
    _as_run(src, root / "dwi" / "tbss" / "demo" / "2026-10-08",
            {"id": "2026-10-08", "label": "MD re-run", "supersedes": ["2026-10-05"]}, keep_measures={"MD"})
    return root


def test_a_reader_reads_0_2_and_not_0_3():
    from neuro_lightbox.spec import readable

    assert readable("0.1.0") and readable("0.2.0") and not readable("0.3.0") and not readable("1.0.0")


def test_runs_of_one_analysis_are_read_together(two_runs):
    scan = SpecScanner(two_runs, "results").scan()
    runs = {v["run"]: v for v in scan.spec_runs.values() if not v.get("merged")}
    assert set(runs) == {"2026-10-05", "2026-10-08"}
    first, second = runs["2026-10-05"], runs["2026-10-08"]
    assert {first["analysis_id"], second["analysis_id"]} == {"dwi/tbss/demo"}
    # the re-run repeats only MD's tests: those of the first run are superseded, the rest stay
    assert second["supersedes"] == ["2026-10-05"] and second["current"]
    assert 0 < first["n_superseded"] < first["n_tests"] and first["current"]
    assert first["superseded_by"] == {"2026-10-08": first["n_superseded"]}
    assert all(x[1:] and x[3] == "2026-10-08" and x[0] == "MD" for x in first["superseded"])
    # the merged view: run 1's current tests and run 2's, each naming its run, listed first
    (mkey,) = [k for k, v in scan.spec_runs.items() if v.get("merged")]
    assert list(scan.spec)[0] == mkey
    _cols, rows = scan.spec[mkey].tables[0].read()
    assert len(rows) == first["n_tests"] - first["n_superseded"] + second["n_tests"]
    assert {r["run"] for r in rows if "MD" in r.values()} == {"2026-10-08"}


def test_runs_share_one_page_one_tab_each(two_runs, tmp_path):
    out = build(BuildConfig(output_dir=tmp_path / "g", results=[SourceInput(two_runs, "results")],
                            render_figures=False), verbose=False)
    m = json.loads((out / "data" / "manifest.json").read_text())
    entries = [e for p in m["paradigms"].values() for e in p.values() if (e.get("spec") or {}).get("run")]
    assert len(entries) == 3 and len({e["meta"]["domain"] for e in entries}) == 1
    by = {e["meta"]["display_name"]: e for e in entries}
    assert list(by)[0] == "Current — all runs"                     # the merged view is the first tab
    first = next(e for k, e in by.items() if k.startswith("Run 2026-10-05 — registered ("))
    assert "Run 2026-10-08 — MD re-run" in by and all(e["summary"].startswith('<p class="spec-run">')
                                                       for e in entries)
    # run 1: its superseded tests struck through in the summary, marked in its embedded table
    assert 'class="spec-superseded"' in first["summary"] and "superseded by run 2026-10-08" in first["summary"]
    assert "this test is superseded by run 2026-10-08" in first["summary"]          # its clusters too
    # (its clusters table too: a superseded test's clusters go with it)
    marked = [sum(1 for r in t["rows"] if r[0] == "2026-10-08")
              for t in first["tables"]["results"] if t["headers"][0] == "superseded_by"]
    assert 2 in marked and all(n > 0 for n in marked)
    # the merged view: each test's run, and each run's correction listed
    merged = by["Current — all runs"]
    assert "<th>Run</th>" in merged["summary"] and 'class="spec-runs"' in merged["summary"]
