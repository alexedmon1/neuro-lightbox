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
