"""The core knows no domain: no bands, no atlas, no analysis package, no study.

NEURO_LIGHTBOX_PLAN.md §6, Phase 2: everything a kind of study brings lives in
its profile (``src/neuro_lightbox/profiles/<name>/``). This fails if any other
file of the package — Python, the app's JavaScript and CSS, the page template —
mentions frequency bands, the Allen atlas, source-analytics, (source)
localization, DUET, or a study by name. Comments and docstrings included: a
core that needs to explain itself in one domain's words has that domain in it.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "neuro_lightbox"
PROFILES = PACKAGE / "profiles"

FORBIDDEN = {
    "frequency bands": r"(?<![a-z])bands?(?![a-z])",
    "the Allen atlas": r"(?<![a-z])allen",
    "source-analytics": r"source[-_ ]?analytics",
    "localization": r"locali[sz]",
    "DUET": r"(?<![a-z])duet(?![a-z])",
    "a study": r"(?<![a-z])(forge|cuprizone|autifony|fxs|aut0020\d)(?![a-z])",
}

SUFFIXES = {".py", ".js", ".css", ".j2", ".html"}


def _core_files():
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or path.suffix not in SUFFIXES or ".min." in path.name:
            continue                                  # vendored libraries are not ours
        if PROFILES in path.parents and path.parent != PROFILES:
            continue                                  # a profile's own folder
        yield path


def test_the_core_names_no_domain():
    hits = []
    for path in _core_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for what, pattern in FORBIDDEN.items():
                if re.search(pattern, line, re.IGNORECASE):
                    hits.append(f"{path.relative_to(PACKAGE)}:{lineno}: {what}: {line.strip()[:100]}")
    assert not hits, "the core mentions a domain:\n" + "\n".join(hits)


def test_the_scan_covers_the_core():
    names = {p.relative_to(PACKAGE).as_posix() for p in _core_files()}
    for expected in ("builder.py", "cli.py", "render.py", "summarize.py", "manifest.py",
                     "profiles/__init__.py", "static/js/app.js", "static/css/main.css",
                     "templates/index.html.j2"):
        assert expected in names
    assert not any(n.startswith("profiles/eeg/") for n in names)
