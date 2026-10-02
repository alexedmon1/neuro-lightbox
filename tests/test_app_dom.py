"""The app's pages, frozen: what a reader of each golden gallery sees.

The golden builds pin what the app is given; this pins what it does with it.
``tests/js/snapshot.cjs`` renders every page of each golden gallery in jsdom —
every route, every table opened, every domain pill and subject shown — and
``tests/golden/<case>/dom.sha256`` records one hash per page. A changed page
fails with its route named; to see how it changed, snapshot the gallery before
and after the change and diff the two (the snapshot prints one tag per line).

Needs Node and jsdom (``npm install --prefix tests/js``); skipped without them.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_golden import CASES, compare_golden

JS = Path(__file__).parent / "js"


def _node_env() -> dict | None:
    if shutil.which("node") is None:
        return None
    env = dict(os.environ)
    paths = [str(JS / "node_modules")] + ([env["NODE_PATH"]] if env.get("NODE_PATH") else [])
    env["NODE_PATH"] = os.pathsep.join(paths)
    probe = subprocess.run(["node", "-e", "require('jsdom')"], env=env, capture_output=True)
    return env if probe.returncode == 0 else None


def snapshot(gallery: Path, env: dict) -> str:
    res = subprocess.run(["node", str(JS / "snapshot.cjs"), str(gallery)], env=env,
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert not res.stderr.strip(), f"the app logged errors:\n{res.stderr[:2000]}"
    return res.stdout


def page_hashes(text: str) -> str:
    """``<sha256>  <route>`` per page, in visiting order."""
    pages: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("=== "):
            pages.append((line[4:], []))
        elif pages:
            pages[-1][1].append(line)
    return "".join(f"{hashlib.sha256(chr(10).join(body).encode()).hexdigest()}  {route}\n"
                   for route, body in pages)


@pytest.mark.parametrize("case", sorted(CASES))
def test_app_pages_match_golden(golden_build, request, case):
    env = _node_env()
    if env is None:
        pytest.skip("needs node and jsdom (npm install --prefix tests/js)")
    gallery = golden_build(case)["_gallery"]
    compare_golden(case, "dom.sha256", page_hashes(snapshot(gallery, env)),
                   request.config.getoption("--update-golden"))
