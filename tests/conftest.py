"""Shared pytest options."""


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden", action="store_true", default=False,
        help="Rewrite tests/golden/ from the current build instead of comparing "
             "against it. Review the git diff of tests/golden/ before committing.",
    )
