"""The MRI profile: results written to neurofaune's results specification.

The core reads the specification (analysis folders, their tables and what each
column means), writes each analysis's summary and draws its effect overview. This
profile adds what MRI brings: slice montages of the significant maps, the display
names of the analysis types, and definitions of the measures.
"""

from __future__ import annotations

from pathlib import Path

from .. import Profile

#: Definitions of the measures, shown on the analyses that report them. No
#: citation is attached: a definition here is not a source.
MEASURES = [
    ("FA", "fractional anisotropy: how directional water diffusion is (0 isotropic, 1 along one axis)"),
    ("MD", "mean diffusivity: the average rate of water diffusion"),
    ("AD", "axial diffusivity: diffusion along the principal direction"),
    ("RD", "radial diffusivity: diffusion perpendicular to the principal direction"),
    ("MK", "mean kurtosis: how far diffusion departs from Gaussian, averaged over directions"),
    ("AK", "axial kurtosis: kurtosis along the principal direction"),
    ("RK", "radial kurtosis: kurtosis perpendicular to the principal direction"),
    ("KFA", "kurtosis fractional anisotropy: how directional the kurtosis is"),
    ("FICVF", "NODDI intracellular volume fraction (neurite density index)"),
    ("ODI", "NODDI orientation dispersion index: how spread neurite orientations are"),
    ("FISO", "NODDI isotropic volume fraction (free water)"),
    ("ReHo", "regional homogeneity: synchrony of a voxel's BOLD time course with its neighbours'"),
    ("fALFF", "fractional amplitude of low-frequency fluctuations of the BOLD signal"),
    ("GM", "grey matter (tissue probability or modulated volume, as the analysis states)"),
    ("WM", "white matter (tissue probability or modulated volume, as the analysis states)"),
]

ANALYSIS_TYPES = {"tbss": "TBSS", "vbm": "VBM", "tbm": "TBM", "voxelwise": "Voxelwise",
                  "roi": "ROI", "covariance_network": "Covariance networks", "nbs": "NBS",
                  "graph": "Graph metrics", "connectome": "Connectomes", "fixel": "Fixel",
                  "other": "Other"}


class MriProfile(Profile):
    name = "mri"
    default_title = "MRI results"

    def render_spec(self, spec, dest: Path, dpi: int, log) -> list:
        from .montage import montages

        return montages(spec, dest, dpi, log)

    def paradigm_labels(self) -> dict:
        return dict(ANALYSIS_TYPES)

    def trim_provenance(self, record: dict) -> dict:
        return record

    def vocabulary(self) -> dict:
        names = "|".join(m for m, _ in MEASURES)
        return {
            "default_title": self.default_title,
            "acronyms": {m.lower(): m for m, _ in MEASURES},
            "glossaries": [{
                "applies_to": ".*",
                "title": "Measures",
                "entries": [{"name": m, "def": d, "cite": ""} for m, d in MEASURES],
                "measure_pattern": names,
            }],
        }
