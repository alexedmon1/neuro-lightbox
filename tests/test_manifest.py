"""Tests for manifest module."""

from pathlib import Path

import pytest

from neuro_lightbox.manifest import build_manifest
from neuro_lightbox.scanner import FigureEntry, ScanResult, TableEntry


@pytest.fixture
def tmp_csv(tmp_path):
    """A table in a tree not written to the results specification."""
    csv = tmp_path / "psd_posthoc_global.csv"
    csv.write_text(
        "contrast,band,hedges_g,significant\n"
        "disease_effect,Low Gamma,1.20,TRUE\n"
        "disease_effect,Delta,-0.30,FALSE\n"
    )
    return csv


def test_build_manifest_basic(tmp_csv):
    scan = ScanResult()
    scan.figures.append(
        FigureEntry(
            src_path="/tmp/fig.png",
            category="analytics",
            source_label="Allen ROI",
            paradigm="resting",
            analysis="psd",
            filename="psd_global.png",
        )
    )
    scan.tables.append(
        TableEntry(
            src_path=tmp_csv,
            source_label="Allen ROI",
            paradigm="resting",
            analysis="psd",
            filename="psd_posthoc_global.csv",
        )
    )
    manifest = build_manifest(scan, "Test Gallery")

    assert manifest["title"] == "Test Gallery"
    assert "Allen ROI" in manifest["sources"]
    assert "resting" in manifest["paradigms"]
    assert "psd" in manifest["paradigms"]["resting"]
    assert manifest["stats"]["total_figures"] == 1
    assert manifest["stats"]["total_tables"] == 1
    # A table the specification does not describe gets no summary from the core,
    # and the MRI profile writes none for it.
    assert manifest["stats"]["total_summaries"] == 0

    psd = manifest["paradigms"]["resting"]["psd"]

    # Figures still reference paths
    assert len(psd["figures"]["Allen ROI"]) == 1

    # Tables are now inline with headers + rows
    tbl = psd["tables"]["Allen ROI"][0]
    assert tbl["filename"] == "psd_posthoc_global.csv"
    # full CSV copied to the gallery for download (inline copy is row-capped)
    assert tbl["csv"] == "tables/resting/psd/psd_posthoc_global.csv"
    assert tbl["headers"] == ["contrast", "band", "hedges_g", "significant"]
    assert len(tbl["rows"]) == 2
    assert tbl["rows"][0] == ["disease_effect", "Low Gamma", "1.20", "TRUE"]

    assert psd["summary"] is None


def test_build_manifest_multi_source(tmp_csv):
    scan = ScanResult()
    for source in ["Allen ROI", "Allen Shell"]:
        scan.figures.append(
            FigureEntry(
                src_path=f"/tmp/{source}/fig.png",
                category="analytics",
                source_label=source,
                paradigm="resting",
                analysis="psd",
                filename="psd_global.png",
            )
        )
        scan.tables.append(
            TableEntry(
                src_path=tmp_csv,
                source_label=source,
                paradigm="resting",
                analysis="psd",
                filename="psd_omnibus.csv",
            )
        )

    manifest = build_manifest(scan, "Multi Source")
    assert len(manifest["sources"]) == 2
    psd = manifest["paradigms"]["resting"]["psd"]
    assert "Allen ROI" in psd["figures"]
    assert "Allen Shell" in psd["figures"]
    assert "Allen ROI" in psd["tables"]
    assert "Allen Shell" in psd["tables"]


def test_build_manifest_empty():
    scan = ScanResult()
    manifest = build_manifest(scan, "Empty")
    assert manifest["stats"]["total_figures"] == 0
    assert manifest["stats"]["paradigm_count"] == 0


def test_manifest_carries_group_display(tmp_csv):
    scan = ScanResult()
    scan.tables.append(TableEntry(src_path=tmp_csv, source_label="ROI", paradigm="resting",
                                  analysis="psd", filename="psd_posthoc_global.csv"))
    manifest = build_manifest(
        scan, "G",
        contrast_labels={"disease_effect": "KO vs WT"},
        contrast_meta={"disease_effect": {"role": "confirmatory", "test": "difference",
                                          "gate_on": []}},
        group_labels={"WT_VEH": "WT Vehicle"}, group_order=["WT_VEH", "KO_VEH"],
    )
    assert manifest["group_labels"] == {"WT_VEH": "WT Vehicle"}
    assert manifest["group_order"] == ["WT_VEH", "KO_VEH"]
    assert manifest["contrast_meta"]["disease_effect"]["role"] == "confirmatory"
