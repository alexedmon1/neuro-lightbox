"""Tests for scanner module."""

from pathlib import Path

import pytest

from neuro_lightbox.scanner import ResultsScanner, _slugify


@pytest.fixture
def tmp_results(tmp_path):
    """Create a mock results directory structure."""
    # Figures
    fig_dir = tmp_path / "figures" / "resting" / "roi_psd"
    fig_dir.mkdir(parents=True)
    (fig_dir / "roi_psd_global.png").write_bytes(b"PNG")
    (fig_dir / "roi_psd_regional.png").write_bytes(b"PNG")

    # Tables
    tbl_dir = tmp_path / "tables" / "resting" / "roi_psd"
    tbl_dir.mkdir(parents=True)
    (tbl_dir / "roi_psd_omnibus.csv").write_text("group_a,group_b,p\n30mgkg,Vehicle,0.05\n")

    return tmp_path


def test_slugify():
    assert _slugify("Allen ROI") == "allen_roi"
    assert _slugify("Hello World!") == "hello_world"


def test_results_scanner(tmp_results):
    scanner = ResultsScanner(tmp_results, "Test Source")
    result = scanner.scan()

    assert len(result.figures) == 2
    assert result.figures[0].paradigm == "resting"
    assert result.figures[0].analysis == "roi_psd"

    assert len(result.tables) == 1
    assert result.tables[0].filename == "roi_psd_omnibus.csv"


def test_results_scanner_recurses_and_accepts_jpeg(tmp_path):
    """source-analytics may nest figures (e.g. per-metric subfolders) and write
    JPEG/WebP as well as PNG; nested paths are flattened into the filename."""
    base = tmp_path / "figures" / "resting" / "roi_connectivity"
    (base / "circos").mkdir(parents=True)
    (base / "circos" / "theta.png").write_bytes(b"PNG")
    (base / "matrix.jpg").write_bytes(b"JPG")
    (base / "notes.txt").write_text("skip me")
    result = ResultsScanner(tmp_path, "Allen ROI").scan()
    names = sorted(f.filename for f in result.figures)
    assert names == ["circos__theta.png", "matrix.jpg"]
    jpg = next(f for f in result.figures if f.filename == "matrix.jpg")
    assert jpg.thumb_rel_path.endswith("/matrix.jpg") and jpg.thumb_rel_path.startswith("thumbs/")
    assert jpg.thumb_rel_path.count(".jpg") == 1


def test_figure_entry_paths(tmp_results):
    scanner = ResultsScanner(tmp_results, "Allen ROI")
    result = scanner.scan()
    fig = result.figures[0]

    assert "allen_roi" in fig.gallery_rel_path
    assert fig.gallery_rel_path.startswith("analytics/")
    assert fig.thumb_rel_path.startswith("thumbs/")
    assert fig.thumb_rel_path.endswith(".jpg")
