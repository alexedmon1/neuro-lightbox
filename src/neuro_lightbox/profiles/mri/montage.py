"""Slice montages of the significant maps of an analysis.

For each test whose corrected p map has voxels below the analysis's alpha, a row
of axial slices through the extent of those voxels: the analysis's background
image (else its mask) in grey, the statistic on the significant voxels in colour.
Tests with no significant voxel get no montage; the summary and the effect overview
list them. A p map that does not say whether it holds p or 1 - p is not
thresholded (the specification's ``values``).
"""

from __future__ import annotations

import re
from pathlib import Path

SLICES = 8


def _load(path: Path):
    import nibabel as nib
    import numpy as np

    img = nib.as_closest_canonical(nib.load(str(path)))
    return np.asarray(img.dataobj, dtype=np.float32), img.affine


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _grow(values, steps: int = 1):
    """Spread each value one voxel in-plane into empty (NaN) neighbours, for drawing a
    one-voxel-thick skeleton visibly. Display only."""
    import numpy as np

    out = values.copy()
    for _ in range(steps):
        grown = out.copy()
        for axis in (0, 1):
            for shift in (1, -1):
                rolled = np.roll(out, shift, axis=axis)
                grown = np.where(np.isnan(grown), rolled, grown)
        out = grown
    return out


def _pick_slices(sig, n: int) -> list[int]:
    import numpy as np

    zs = np.flatnonzero(sig.any(axis=(0, 1)))
    if len(zs) <= n:
        return [int(z) for z in zs]
    return [int(zs[i]) for i in np.linspace(0, len(zs) - 1, n).round().astype(int)]


def montage(stat_path: Path, p_path: Path, values: str, background_path: Path | None,
            mask_path: Path | None, alpha: float, title: str, out_path: Path, dpi: int,
            thicken: bool) -> Path | None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    t, aff = _load(stat_path)
    pv, _ = _load(p_path)
    p = 1.0 - pv if values == "one_minus_p" else pv
    inside = _load(mask_path)[0] > 0 if mask_path is not None else np.abs(t) > 0
    sig = inside & (p < alpha)
    if not sig.any():
        return None
    if background_path is not None:
        bg = _load(background_path)[0]
        nz = bg[bg != 0]
        lo, hi = (np.percentile(nz, [1, 99]) if nz.size else (0.0, 1.0))
        if hi <= lo:
            hi = lo + 1.0
    else:                                          # no image: the mask itself, mid grey
        bg, lo, hi = inside.astype(np.float32), 0.0, 2.5
    zs = _pick_slices(sig, SLICES)
    vals = np.where(sig, t, np.nan)
    if thicken:
        vals = _grow(vals)
    vmin, vmax = float(np.min(t[sig])), float(np.max(t[sig]))
    if vmax <= vmin:
        vmax = vmin + 1e-6
    fig, axes = plt.subplots(1, len(zs), figsize=(1.7 * len(zs) + 0.8, 2.6), squeeze=False)
    im = None
    for ax, z in zip(axes[0], zs):
        ax.imshow(bg[:, :, z].T, cmap="gray", origin="lower", vmin=lo, vmax=hi)
        im = ax.imshow(vals[:, :, z].T, cmap="autumn", origin="lower", vmin=vmin, vmax=vmax)
        zmm = (aff @ np.array([0, 0, z, 1.0]))[2]
        ax.set_title(f"z = {zmm:.1f} mm", fontsize=7)
        ax.set_xticks([])
        ax.set_yticks([])
    axes[0][-1].text(1.02, 0.5, "R", transform=axes[0][-1].transAxes, fontsize=8, va="center")
    cb = fig.colorbar(im, ax=list(axes[0]), fraction=0.02, pad=0.01)
    cb.set_label("statistic", fontsize=7)
    fig.suptitle(title, fontsize=8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_path


def montages(spec, dest: Path, dpi: int, log) -> list[Path]:
    """One montage per test with significant voxels (see module docstring)."""
    stats = {(m.get("measure", ""), m.get("contrast", "")): m for m in spec.maps("stat")}
    pmaps = {(m.get("measure", ""), m.get("contrast", "")): m for m in spec.maps("p_corrected")}
    background = next((spec.file(m["path"]) for m in spec.maps("background")
                       if spec.file(m.get("path", ""))), None)
    mask = next((spec.file(m["path"]) for m in spec.maps("mask") if spec.file(m.get("path", ""))), None)
    thicken = spec.analysis_type == "tbss"
    tests = spec.tables_with_role("tests")
    pkind = (tests[0].qualifier("p_value", "PKind") if tests else None) or "corrected"
    out = []
    order = {m: i for i, m in enumerate(spec.measures)}
    for key in sorted(stats, key=lambda k: (order.get(k[0], len(order)), k)):
        pm = pmaps.get(key)
        if pm is None or pm.get("values") not in ("p", "one_minus_p"):
            if pm is not None:
                log(f"  WARNING: {spec.id}: {pm.get('path')} does not say whether it holds p or "
                    "1 - p; not thresholded")
            continue
        stat_path, p_path = spec.file(stats[key].get("path", "")), spec.file(pm.get("path", ""))
        if stat_path is None or p_path is None:
            continue
        measure, contrast = key
        title = (f"{measure} · {contrast}: voxels at {pkind} p < {spec.alpha:g}, statistic shown"
                 + ("; skeleton thickened for display" if thicken else ""))
        path = montage(stat_path, p_path, pm["values"], background, mask, spec.alpha, title,
                       dest / f"montage_{_slug(measure)}_{_slug(contrast)}.png", dpi, thicken)
        if path is not None:
            out.append(path)
    return out
