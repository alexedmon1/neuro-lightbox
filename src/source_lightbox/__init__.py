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

# Old module name -> where it lives now. The two render workers are not among
# them: they run by path in source-analytics' interpreter, never imported here.
# Names that moved into the EEG profile from a module the core kept (e.g. the
# renderers in `render`) are imported from `neuro_lightbox.profiles.eeg`.
_MODULES = {
    "builder": "neuro_lightbox.builder",
    "cli": "neuro_lightbox.cli",
    "config": "neuro_lightbox.config",
    "manifest": "neuro_lightbox.manifest",
    "render": "neuro_lightbox.render",
    "scanner": "neuro_lightbox.scanner",
    "summarize": "neuro_lightbox.summarize",
    "thumbnails": "neuro_lightbox.thumbnails",
    "brain_mosaic": "neuro_lightbox.profiles.eeg.brain_mosaic",
    "circos": "neuro_lightbox.profiles.eeg.circos",
    "qc_meta": "neuro_lightbox.profiles.eeg.qc_meta",
    "_worker_atlas": "neuro_lightbox.profiles.eeg._worker_atlas",
}

for _name, _target in _MODULES.items():
    _module = importlib.import_module(_target)
    sys.modules[f"{__name__}.{_name}"] = _module
    globals()[_name] = _module
