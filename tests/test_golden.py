"""Golden builds: whole galleries built from fixture trees, frozen.

The regression net for the neuro-lightbox work (NEURO_LIGHTBOX_PLAN.md §6,
Phase 0). Each case builds a gallery through the CLI from a fixture under
``tests/fixtures/`` and compares it with what ``tests/golden/<case>/`` recorded:

- ``manifest.json`` — every table, digest, figure entry, label and provenance
  block the app is given, one table row per line so a diff reads as rows (the
  build's own bytes are pinned by their hash in ``files.txt``);
- ``index.html`` — the page around it (build timestamp, and the inlined manifest
  and profile vocabulary, normalised out);
- ``files.txt`` — every file the build wrote, with a hash for everything that is
  copied rather than drawn, and for the manifest;
- ``figures.sha256`` — the rendered figures, compared only under the
  matplotlib / numpy / Pillow versions that recorded them.

A change in any of them fails the test. When the change is intended, rerun with
``--update-golden`` and review ``git diff tests/golden/`` — that diff is the
record of what the change did to a gallery.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"

# name -> (fixture folder, extra CLI args).
CASES = {
    "mri_h1c": ("mri_h1c", []),
    "mri_spec": ("mri_spec", []),
}

_VERSIONS = ("matplotlib", "numpy", "PIL")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _readable(obj, depth: int = 0) -> str:
    """JSON with nesting indented but each list of scalars (a table row, a
    header) on one line. The build writes one cell per line, which makes a
    golden manifest several times larger and its diffs unreadable."""
    pad = "  " * (depth + 1)
    if isinstance(obj, dict) and obj:
        items = (f"{pad}{json.dumps(k, ensure_ascii=False)}: {_readable(v, depth + 1)}"
                 for k, v in obj.items())
        return "{\n" + ",\n".join(items) + "\n" + "  " * depth + "}"
    if isinstance(obj, list) and any(isinstance(x, (dict, list)) for x in obj):
        items = (pad + _readable(v, depth + 1) for v in obj)
        return "[\n" + ",\n".join(items) + "\n" + "  " * depth + "]"
    return json.dumps(obj, ensure_ascii=False)


def _versions() -> str:
    import importlib

    return " ".join(f"{m}={importlib.import_module(m).__version__}" for m in _VERSIONS)


def _build(case: str, root: Path) -> dict:
    """Build one case; return its golden artefacts as {name: text}, and the
    built gallery's folder under ``"_gallery"``."""
    from click.testing import CliRunner

    from neuro_lightbox.cli import main

    fixture_name, extra = CASES[case]
    fixture = FIXTURES / fixture_name
    if not (fixture / "study.yaml").is_file():
        pytest.skip(f"fixture {fixture_name}/ has no study.yaml")
    out = root / "gallery"
    res = CliRunner().invoke(
        main, ["build", "--config", str(fixture / "study.yaml"), "--output", str(out),
               "--quiet", *extra], catch_exceptions=False)
    assert res.exit_code == 0, res.output

    manifest = (out / "data" / "manifest.json").read_text(encoding="utf-8")
    html = (out / "index.html").read_text(encoding="utf-8")
    html = re.sub(r"\?v=\d+", "?v=<build_ts>", html)
    # The manifest and the profile's vocabulary are inlined, escaped for a
    # <script>; their bytes are pinned by their hashes in files.txt.
    from neuro_lightbox.builder import _script_safe

    profile = (out / "data" / "profile.json").read_text(encoding="utf-8")
    for name, text in (("manifest.json", manifest), ("profile.json", profile)):
        assert _script_safe(text) in html, f"index.html does not inline data/{name}"
        html = html.replace(_script_safe(text), f"<{name}>")

    files, figures = [], []
    for p in sorted(out.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(out).as_posix()
        drawn = rel.startswith("figures/") or rel == "index.html"   # index.html: build_ts
        files.append(rel if drawn else f"{rel}  {_sha(p)}")
        if rel.startswith("figures/analytics/"):
            figures.append(f"{rel}  {_sha(p)}")

    return {
        "manifest.json": _readable(json.loads(manifest)) + "\n",
        "index.html": html,
        "files.txt": "\n".join(files) + "\n",
        "figures.sha256": f"# {_versions()}\n" + "\n".join(figures) + "\n",
        "_gallery": out,
    }


def compare_golden(case: str, name: str, actual: str, update: bool) -> None:
    path = GOLDEN / case / name
    if update:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        return
    expected = path.read_text(encoding="utf-8") if path.exists() else ""
    if actual == expected:
        return
    diff = list(difflib.unified_diff(
        expected.splitlines(), actual.splitlines(),
        f"golden/{case}/{name}", f"build/{case}/{name}", lineterm="", n=2))
    shown = "\n".join(diff[:200]) + (f"\n... {len(diff) - 200} more lines" if len(diff) > 200 else "")
    pytest.fail(f"{case}: {name} differs from the golden build "
                f"(rerun with --update-golden if intended):\n{shown}", pytrace=False)


@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("name", ["manifest.json", "index.html", "files.txt"])
def test_gallery_matches_golden(golden_build, request, case, name):
    compare_golden(case, name, golden_build(case)[name],
                   request.config.getoption("--update-golden"))


@pytest.mark.parametrize("case", sorted(CASES))
def test_rendered_figures_match_golden(golden_build, request, case):
    actual = golden_build(case)["figures.sha256"]
    update = request.config.getoption("--update-golden")
    path = GOLDEN / case / "figures.sha256"
    if not update and path.exists():
        recorded = path.read_text(encoding="utf-8").splitlines()[0]
        if recorded != actual.splitlines()[0]:
            pytest.skip(f"figure hashes were recorded under {recorded[2:]}; this is "
                        f"{actual.splitlines()[0][2:]}")
    compare_golden(case, "figures.sha256", actual, update)
