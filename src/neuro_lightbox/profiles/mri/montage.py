"""Slice montages of the significant maps of an analysis.

For each test whose corrected p map has voxels below the analysis's alpha, a row of
slices through the extent of those voxels: the analysis's background image (the
atlas template; else its mask) in grey, the statistic on the significant voxels in
colour. Tests with no significant voxel get no montage; the summary and the effect
overview list them. A p map that does not say whether it holds p or 1 - p is not
thresholded (the specification's ``values``).

Orientation comes from the map's declared ``axes`` (the anatomical direction each
voxel axis runs), not the image header, which for animals often follows the scanner;
without ``axes`` the header is used and the montage says so. Slices are cut in the
analysis's ``display.plane`` (axial by default) and drawn superior / anterior up,
the subject's right on the right, both sides labelled.
"""

from __future__ import annotations

import re
from pathlib import Path

SLICES = 8
#: plane -> the RAS axis the slices are cut across, and the two in-plane axes' end labels
PLANES = {"axial": (2, ("L", "R"), ("P", "A")),
          "coronal": (1, ("L", "R"), ("I", "S")),
          "sagittal": (0, ("P", "A"), ("I", "S"))}
ALONG = {"axial": "inferior to superior", "coronal": "posterior to anterior",
         "sagittal": "left to right"}


def _load(path: Path, axes: str | None):
    """The image as an array whose axes run toward R, A, S (anatomically)."""
    import nibabel as nib
    import numpy as np
    from nibabel.orientations import apply_orientation, axcodes2ornt, ornt_transform

    img = nib.load(str(path))
    if axes:
        ornt = ornt_transform(axcodes2ornt(tuple(axes.upper())), axcodes2ornt(("R", "A", "S")))
        return apply_orientation(np.asarray(img.dataobj, dtype=np.float32), ornt)
    return np.asarray(nib.as_closest_canonical(img).dataobj, dtype=np.float32)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _grow(values, cut: int, steps: int = 1):
    """Spread each value one voxel in-plane into empty (NaN) neighbours, for drawing a
    one-voxel-thick skeleton visibly. Display only."""
    import numpy as np

    out = values.copy()
    for _ in range(steps):
        grown = out.copy()
        for axis in (a for a in range(3) if a != cut):
            for shift in (1, -1):
                rolled = np.roll(out, shift, axis=axis)
                grown = np.where(np.isnan(grown), rolled, grown)
        out = grown
    return out


def _pick_slices(sig, cut: int, n: int) -> list[int]:
    import numpy as np

    other = tuple(a for a in range(3) if a != cut)
    ks = np.flatnonzero(sig.any(axis=other))
    if len(ks) <= n:
        return [int(k) for k in ks]
    return [int(ks[i]) for i in np.linspace(0, len(ks) - 1, n).round().astype(int)]


def montage(stat_path: Path, p_path: Path, values: str, background_path: Path | None,
            mask_path: Path | None, alpha: float, title: str, out_path: Path, dpi: int,
            thicken: bool, axes: str | None = None, plane: str = "axial") -> Path | None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    cut, (left, right), (down, up) = PLANES[plane]
    t = _load(stat_path, axes)
    pv = _load(p_path, axes)
    p = 1.0 - pv if values == "one_minus_p" else pv
    inside = _load(mask_path, axes) > 0 if mask_path is not None else np.abs(t) > 0
    sig = inside & (p < alpha)
    if not sig.any():
        return None
    if background_path is not None:
        bg = _load(background_path, axes)
        nz = bg[bg != 0]
        lo, hi = (np.percentile(nz, [1, 99]) if nz.size else (0.0, 1.0))
        if hi <= lo:
            hi = lo + 1.0
    else:                                          # no image: the mask itself, mid grey
        bg, lo, hi = inside.astype(np.float32), 0.0, 2.5
    ks = _pick_slices(sig, cut, SLICES)
    vals = np.where(sig, t, np.nan)
    if thicken:
        vals = _grow(vals, cut)
    vmin, vmax = float(np.min(t[sig])), float(np.max(t[sig]))
    if vmax <= vmin:
        vmax = vmin + 1e-6
    fig, panels = plt.subplots(1, len(ks), figsize=(1.7 * len(ks) + 0.8, 2.7), squeeze=False)
    im = None
    for ax, k in zip(panels[0], ks):
        ax.imshow(np.take(bg, k, axis=cut).T, cmap="gray", origin="lower", vmin=lo, vmax=hi)
        im = ax.imshow(np.take(vals, k, axis=cut).T, cmap="autumn", origin="lower", vmin=vmin, vmax=vmax)
        ax.set_title(f"slice {k + 1}/{bg.shape[cut]}", fontsize=7)
        ax.set_xticks([])
        ax.set_yticks([])
        for x, y, s in ((0.02, 0.02, left), (0.98, 0.02, right), (0.5, 0.98, up)):
            ax.text(x, y, s, transform=ax.transAxes, fontsize=6, color="white",
                    ha="left" if x < 0.5 else "right" if x > 0.5 else "center",
                    va="bottom" if y < 0.5 else "top")
    cb = fig.colorbar(im, ax=list(panels[0]), fraction=0.02, pad=0.01)
    cb.set_label("statistic", fontsize=7)
    how = (f"{plane} slices, {ALONG[plane]}; orientation as declared ({axes})" if axes
           else f"{plane} slices, {ALONG[plane]}; orientation from the image header (not declared)")
    fig.suptitle(f"{title}\n{how}", fontsize=8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_path


def montages(spec, dest: Path, dpi: int, log) -> list[Path]:
    """One montage per test with significant voxels (see module docstring)."""
    def key(m):
        return (m.get("facet", ""), m.get("measure", ""), m.get("contrast", ""))

    stats = {key(m): m for m in spec.maps("stat")}            # in the analysis's own order
    pmaps = {key(m): m for m in spec.maps("p_corrected")}
    background = next((spec.file(m["path"]) for m in spec.maps("background")
                       if spec.file(m.get("path", ""))), None)
    mask = next((spec.file(m["path"]) for m in spec.maps("mask") if spec.file(m.get("path", ""))), None)
    plane = ((spec.record.get("display") or {}).get("plane")) or "axial"
    if plane not in PLANES:
        log(f"  WARNING: {spec.id}: display plane {plane!r} unknown; axial used")
        plane = "axial"
    declared = {m.get("axes") for m in spec.maps() if m.get("axes")}
    if len(declared) > 1:
        log(f"  WARNING: {spec.id}: maps declare different axes {sorted(declared)}; no montages")
        return []
    axes = declared.pop() if declared else None
    thicken = spec.analysis_type == "tbss"
    tests = spec.tables_with_role("tests")
    pkind = (tests[0].qualifier("p_value", "PKind") if tests else None) or "corrected"
    out = []
    for k, sm in stats.items():
        pm = pmaps.get(k)
        if pm is None or pm.get("values") not in ("p", "one_minus_p"):
            if pm is not None:
                log(f"  WARNING: {spec.id}: {pm.get('path')} does not say whether it holds p or "
                    "1 - p; not thresholded")
            continue
        stat_path, p_path = spec.file(sm.get("path", "")), spec.file(pm.get("path", ""))
        if stat_path is None or p_path is None:
            continue
        facet, measure, contrast = k
        title = (" · ".join(x for x in (facet, measure, contrast) if x)
                 + f": voxels at {pkind} p < {spec.alpha:g}, statistic shown"
                 + ("; skeleton thickened for display" if thicken else ""))
        name = "_".join(_slug(x) for x in (facet, measure, contrast) if x)
        path = montage(stat_path, p_path, pm["values"], background, mask, spec.alpha, title,
                       dest / f"montage_{name}.png", dpi, thicken, axes=axes, plane=plane)
        if path is not None:
            out.append(path)
    return out
