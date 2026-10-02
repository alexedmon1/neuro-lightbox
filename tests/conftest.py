"""Shared pytest options and fixtures."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden", action="store_true", default=False,
        help="Rewrite tests/golden/ from the current build instead of comparing "
             "against it. Review the git diff of tests/golden/ before committing.",
    )


@pytest.fixture(scope="session")
def golden_build(tmp_path_factory):
    """``golden_build(case)`` builds a golden case once per session (see
    test_golden.py) and returns its artefacts and gallery folder."""
    from tests.test_golden import _build

    cache: dict[str, dict] = {}

    def get(case: str) -> dict:
        if case not in cache:
            cache[case] = _build(case, tmp_path_factory.mktemp(case))
        return cache[case]

    return get
