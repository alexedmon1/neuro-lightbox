"""The old name keeps working: ``source-lightbox`` and ``source_lightbox``.

Deprecated aliases for the scripts written before the rename. Each warns, and
each builds the same gallery as the new name.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

from tests.test_golden import FIXTURES, GOLDEN, _readable


def test_the_old_import_name_warns():
    res = subprocess.run([sys.executable, "-W", "error::DeprecationWarning", "-c",
                          "import source_lightbox"], capture_output=True, text=True)
    assert res.returncode != 0
    assert "source_lightbox is now neuro_lightbox" in res.stderr


def test_the_old_modules_are_the_new_modules():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import source_lightbox

    import neuro_lightbox

    assert source_lightbox.__version__ == neuro_lightbox.__version__
    for name, target in source_lightbox._MODULES.items():
        assert sys.modules[f"source_lightbox.{name}"] is sys.modules[target], name


def _build_with(command: list[str], tmp_path):
    out = tmp_path / "gallery"
    res = subprocess.run(
        [*command, "build", "--config", str(FIXTURES / "eeg_legacy" / "study.yaml"),
         "--output", str(out), "--quiet", "--brain-python", str(tmp_path / "none")],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    manifest = json.loads((out / "data" / "manifest.json").read_text(encoding="utf-8"))
    return res, _readable(manifest) + "\n"


@pytest.mark.parametrize("command", [["source-lightbox"], ["neuro-lightbox"]])
def test_both_commands_build_the_golden_gallery(command, tmp_path):
    if shutil.which(command[0]) is None:
        pytest.skip(f"{command[0]} is not on PATH (run under `uv run pytest`)")
    res, manifest = _build_with(command, tmp_path)
    assert manifest == (GOLDEN / "eeg_legacy" / "manifest.json").read_text(encoding="utf-8")
    deprecated = "source-lightbox is now neuro-lightbox" in res.stderr
    assert deprecated == (command[0] == "source-lightbox")


def test_python_dash_m_old_name_builds_the_golden_gallery(tmp_path):
    res, manifest = _build_with([sys.executable, "-m", "source_lightbox"], tmp_path)
    assert manifest == (GOLDEN / "eeg_legacy" / "manifest.json").read_text(encoding="utf-8")
    assert "source-lightbox is now neuro-lightbox" in res.stderr
