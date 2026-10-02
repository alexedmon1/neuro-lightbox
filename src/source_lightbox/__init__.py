"""source-lightbox is now neuro-lightbox: this name is a deprecated alias.

``import source_lightbox.cli`` (and every other module) gives the same module
object as ``neuro_lightbox.cli``, so code written against the old name — a
monkeypatch included — behaves exactly as before. It warns once, on import.
"""

import importlib
import sys
import warnings

warnings.warn(
    "source_lightbox is now neuro_lightbox; import neuro_lightbox instead. "
    "The old name will be removed in a future release.",
    DeprecationWarning, stacklevel=2,
)

from neuro_lightbox import __version__  # noqa: E402

# The importable modules. The two render workers are not among them: they run
# by path in source-analytics' interpreter, never imported here.
_MODULES = ("brain_mosaic", "builder", "circos", "cli", "config", "manifest", "qc_meta",
            "render", "scanner", "summarize", "thumbnails", "_worker_atlas")

for _name in _MODULES:
    _module = importlib.import_module(f"neuro_lightbox.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _module
    globals()[_name] = _module
