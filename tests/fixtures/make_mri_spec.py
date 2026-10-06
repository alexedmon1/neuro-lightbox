"""Write ``mri_spec/results/``: two synthetic analyses in neurofaune's results specification.

Every value is synthetic -- invented subjects, invented groups, effects planted by
this script. The folders are written by neurofaune's own writer
(``neurofaune.analysis.stats.readout.read_randomise`` and
``neurofaune.analysis.stats.readout_results.write_readout_results``, strict), so
they conform to the specification (``neurofaune/docs/RESULTS_SPEC.md``, 0.1.0) by
construction. No FSL: the randomise outputs (t, 1 - FWE p, 1 - uncorrected p) are
written by hand, as neurofaune's ``tests/unit/test_tbss_readout.py`` does, with t
computed from the synthetic per-subject data and the p maps coherent with the
planted effects.

Rerun with neurofaune's environment (it needs neurofaune, numpy, nibabel, pandas)::

    ~/sandbox/neurofaune/.venv/bin/python tests/fixtures/make_mri_spec.py
    ~/sandbox/neurofaune/.venv/bin/neurofaune results check tests/fixtures/mri_spec/results

Deterministic (seeded). After writing, the provenance records are scrubbed of what
would differ run to run or leak a local path -- timestamps fixed, the install's
``file://`` CodeURL dropped, the platform string generalised -- and the folders are
checked again.

Planted truth:

* ``tbss/demo`` (two groups, treated n = 12 vs control n = 10; FA, MD, MK):
  MD higher in treated in a corpus-callosum block that crosses the midline
  (treated>control FWE-significant, one cluster); MK lower in treated in the same
  block and in a right internal-capsule block (control>treated FWE-significant,
  two clusters, one crossing the midline); FA has no effect (no FWE voxel in
  either direction, a few uncorrected-only voxels). The other directions are nulls.
* ``vbm/demo_change`` (one sample, treated n = 12, GM change): an increase in a
  right-striatum blob (increase FWE-significant, one cluster, not crossing the
  midline); nothing for decrease. No background image and no declared axes -- a reader
  draws on the mask and orients by the header.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np

from neurofaune.analysis.stats.design_record import (read_design_record, render_design_markdown,
                                                     write_design)
from neurofaune.analysis.stats.readout import Atlas, read_randomise
from neurofaune.analysis.stats.readout_results import write_readout_results
from neurofaune.results import check

HERE = Path(__file__).resolve().parent
ROOT = HERE / "mri_spec" / "results"
VOX = 0.3
FIXED_TIME = "2026-10-06T00:00:00+00:00"
CAVEAT = ("Synthetic fixture: every subject, group and value is invented, and the effects "
          "were planted by tests/fixtures/make_mri_spec.py.")


def _affine(shape) -> np.ndarray:
    aff = np.diag([VOX, VOX, VOX, 1.0])
    aff[:3, 3] = -VOX * (np.asarray(shape) - 1) / 2          # centred: x = 0 at the midline
    return aff


def _save(path: Path, data, aff, dtype=np.float32) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = nib.Nifti1Image(np.asarray(data, dtype=dtype), aff)
    img.header.set_xyzt_units("mm")
    nib.save(img, str(path))
    return path


def _two_sample_t(data: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    xa, xb = data[..., a], data[..., b]
    na, nb = a.sum(), b.sum()
    sp = np.sqrt(((na - 1) * xa.var(-1, ddof=1) + (nb - 1) * xb.var(-1, ddof=1)) / (na + nb - 2))
    return (xa.mean(-1) - xb.mean(-1)) / (sp * np.sqrt(1 / na + 1 / nb) + 1e-12)


def _one_sample_t(data: np.ndarray) -> np.ndarray:
    n = data.shape[-1]
    return data.mean(-1) / (data.std(-1, ddof=1) / np.sqrt(n) + 1e-12)


def _write_maps(run_dir: Path, aff, mask, maps: list[tuple]) -> None:
    """maps: [(t, corrp, p)] per contrast, already zero outside the mask."""
    for c, (t, corrp, p) in enumerate(maps, start=1):
        _save(run_dir / f"randomise_tstat{c}.nii.gz", np.round(np.where(mask, t, 0), 3), aff)
        _save(run_dir / f"randomise_tfce_corrp_tstat{c}.nii.gz", np.where(mask, corrp, 0), aff)
        _save(run_dir / f"randomise_tfce_p_tstat{c}.nii.gz", np.where(mask, p, 0), aff)


def _scrub(folder: Path) -> None:
    prov_path = folder / "provenance.json"
    prov = json.loads(prov_path.read_text())
    for g in prov["generated_by"]:
        if str(g.get("CodeURL", "")).startswith("file:"):
            del g["CodeURL"]
        if "DateTime" in g:
            g["DateTime"] = FIXED_TIME
    prov["run"]["start"] = prov["run"]["end"] = FIXED_TIME
    prov["environment"] = {"python": prov["environment"]["python"], "platform": "Linux"}
    prov_path.write_text(json.dumps(prov, indent=2) + "\n")
    for rec in folder.rglob("design.json"):
        d = json.loads(rec.read_text())
        wb = d.get("written_by") or {}
        if str(wb.get("CodeURL", "")).startswith("file:"):
            del wb["CodeURL"]
        for key in ("DateTime", "written"):
            if key in wb:
                wb[key] = FIXED_TIME
        if "written" in d:
            d["written"] = FIXED_TIME
        rec.write_text(json.dumps(d, indent=2) + "\n")
        rec.with_suffix(".md").write_text(render_design_markdown(d))


# ------------------------------------------------------------------- TBSS ---
def tbss(rng, work: Path) -> Path:
    out = ROOT / "tbss" / "demo"
    shape = (40, 48, 24)
    aff = _affine(shape)
    nx = shape[0]
    mid = (nx - 1) / 2

    skel = np.zeros(shape, bool)
    parc = np.zeros(shape, np.int32)
    cc_block = np.zeros(shape, bool)
    ic_block = np.zeros(shape, bool)
    names = {1: "Corpus.Callosum.and.Associated.Subcortical.White.Matter.L",
             2: "Corpus.Callosum.and.Associated.Subcortical.White.Matter.R",
             3: "Internal.Capsule.L", 4: "Internal.Capsule.R",
             5: "Fimbria.of.the.Hippocampus.L", 6: "Fimbria.of.the.Hippocampus.R",
             7: "Anterior.Commissure.anterior.part.L", 8: "Anterior.Commissure.anterior.part.R"}
    hemi = {k: v[-1] for k, v in names.items()}

    def put(i, j, k, left_label):
        skel[i, j, k] = True
        parc[i, j, k] = left_label + (0 if i < mid else 1)   # x < 0 is left

    for i in range(6, 34):                                  # corpus callosum: an arched sheet
        k = 15 - int(round(((i - mid) / 10) ** 2 * 2))
        for j in range(16, 33):
            put(i, j, k, 1)
            if 13 <= i <= 26 and 20 <= j <= 28:
                cc_block[i, j, k] = True
    for i in (12, 27):                                      # internal capsules: vertical sheets
        for j in range(18, 31):
            for k in range(6, 12):
                put(i, j, k, 3)
                if i == 27 and 20 <= j <= 28 and k <= 10:
                    ic_block[i, j, k] = True
    for i in (9, 30):                                       # fimbriae: curved lines
        for j in range(32, 42):
            put(i, j, 8 + (j - 32) // 4, 5)
    for i in range(13, 27):                                 # anterior commissure: a line across
        put(i, 11, 8, 7)

    groups = np.array(["treated"] * 12 + ["control"] * 10)
    a, b = groups == "treated", groups == "control"
    n = len(groups)
    rows = [f"sub-{i + 1:02d}" for i in range(n)]

    X = np.column_stack([a, b]).astype(float)
    write_design(out, X,
                 [("treated", "1 if the animal is in the treated group, else 0", "group"),
                  ("control", "1 if the animal is in the control group, else 0", "group")],
                 [{"name": "treated>control", "vector": [1, -1], "test_kind": "two_group",
                   "group_a": "treated", "group_b": "control",
                   "tests": "treated mean > control mean"},
                  {"name": "control>treated", "vector": [-1, 1], "test_kind": "two_group",
                   "group_a": "control", "group_b": "treated",
                   "tests": "control mean > treated mean"}],
                 rows=rows, groups={"treated": 12, "control": 10},
                 data={"file": "all_<measure>_skeletonised.nii.gz",
                       "meaning": "each animal's synthetic value on the TBSS skeleton"},
                 summary="Do treated animals differ from controls on the skeleton? (synthetic)")
    record = read_design_record(out)

    measures = {"FA": (0.45, 0.03), "MD": (7.0e-4, 3.0e-5), "MK": (1.0, 0.05)}
    run_dirs, tests_all, clusters_all = {}, [], []
    atlas = Atlas(parc, names, hemi)
    lone = [(8, 20, 15 - int(round(((8 - mid) / 10) ** 2 * 2))), (27, 25, 7), (14, 11, 8)]
    for m, (base, sd) in measures.items():
        # voxel noise plus a per-animal offset shared by every voxel, as real data have;
        # the offsets are centred within each group so a null measure has no whole-mask effect
        offset = rng.standard_normal(n)
        for g in (a, b):
            offset[g] -= offset[g].mean()
        data = base + sd * (rng.standard_normal(shape + (n,)) + offset)
        if m == "MD":
            data[cc_block] += 2.5 * sd * a
        if m == "MK":
            data[cc_block | ic_block] -= 3.0 * sd * a
        data[~skel] = 0
        data = data.astype(np.float32)
        data_path = _save(work / f"all_{m}.nii.gz", data, aff)
        t = _two_sample_t(data.astype(float), a, b)

        planted = {"MD": (cc_block, None), "MK": (None, cc_block | ic_block), "FA": (None, None)}[m]
        maps = []
        for c, sign in ((0, 1), (1, -1)):
            block = planted[c]
            corrp = np.full(shape, 0.35 if m != "FA" else 0.2)
            p = np.full(shape, 0.5)
            if block is not None:
                corrp[block] = 0.99
                p[block] = 0.998
            if m == "FA" and c == 0:
                for v in lone:                              # uncorrected-only hits, no FWE
                    p[v] = 0.97
            maps.append((sign * t, corrp, p))
        rd = out / f"randomise_{m}"
        _write_maps(rd, aff, skel, maps)
        run_dirs[m] = rd

        mask_path = _save(work / "mask.nii.gz", skel, aff, np.uint8)
        tests, clusters = read_randomise(rd, data_path, out / "design.mat", mask_path,
                                         atlas=atlas, cluster_on="fwe", alpha=0.05,
                                         min_cluster_size=10, labels={"metric": m})
        tests_all.append(tests)
        clusters_all.append(clusters)

    import pandas as pd
    tests = pd.concat(tests_all, ignore_index=True)
    clusters = pd.concat([c for c in clusters_all if len(c)], ignore_index=True)

    xs = (np.arange(nx) - mid) / (nx / 2.2)
    ys = (np.arange(shape[1]) - (shape[1] - 1) / 2) / (shape[1] / 2.2)
    zs = (np.arange(shape[2]) - (shape[2] - 1) / 2) / (shape[2] / 2.2)
    r2 = xs[:, None, None] ** 2 + ys[None, :, None] ** 2 + zs[None, None, :] ** 2
    # A stand-in for the atlas's intensity template (what readers draw maps on): a brain
    # with a brighter rim and darker core, not a study-derived image.
    brain = np.where(r2 < 1, 40 + 50 * r2, 0)
    background = _save(work / "template.nii.gz", np.round(brain, 1), aff)

    write_readout_results(
        out, tests, clusters, analysis_id="tbss/demo", title="TBSS: demo (synthetic)",
        description=record["summary"], analysis_type="tbss", modality="dwi",
        measure_column="metric", measures=list(measures), run_dirs=run_dirs,
        n_permutations=5000, alpha=0.05, mask_name="TBSS skeleton", space="SIGMA",
        inference="2-D TFCE", role="confirmatory", design_record=record, started=FIXED_TIME,
        inputs=[{"path": f"all_{m}_skeletonised.nii.gz", "role": f"skeletonised {m} (synthetic)"}
                for m in measures],
        settings={"n_permutations": 5000, "tfce": True, "cluster_threshold": 0.95,
                  "min_cluster_size": 10, "seed": 2026},
        caveats=[CAVEAT], mask=mask_path, background=background, axes="RAS", plane="axial",
        strict=True)
    return out


# -------------------------------------------------------------------- VBM ---
def vbm(rng, work: Path) -> Path:
    out = ROOT / "vbm" / "demo_change"
    shape = (24, 28, 16)
    aff = _affine(shape)
    c = (np.asarray(shape) - 1) / 2
    ii, jj, kk = np.meshgrid(*(np.arange(s) for s in shape), indexing="ij")
    brain = ((ii - c[0]) / 10.5) ** 2 + ((jj - c[1]) / 12.5) ** 2 + ((kk - c[2]) / 7) ** 2 < 1
    blob = ((ii - (c[0] + 5)) ** 2 + (jj - (c[1] + 2)) ** 2 + (kk - c[2]) ** 2 <= 9) & brain

    parc = np.zeros(shape, np.int32)
    right = ii > c[0]
    names = {1: "Cortex.L", 2: "Cortex.R", 3: "Striatum.L", 4: "Striatum.R",
             5: "Hippocampus.L", 6: "Hippocampus.R"}
    hemi = {k: v[-1] for k, v in names.items()}
    deep = ((ii - c[0]) / 10.5) ** 2 + ((jj - c[1]) / 12.5) ** 2 + ((kk - c[2]) / 7) ** 2 < 0.45
    parc[brain] = 1
    parc[brain & deep & (jj >= c[1] - 3)] = 3
    parc[brain & deep & (jj < c[1] - 3)] = 5
    parc[brain & right] += 1

    n = 12
    rows = [f"sub-{i + 1:02d}" for i in range(n)]
    write_design(out, np.ones((n, 1)),
                 [("intercept", "1 for every treated animal: the mean change", "intercept")],
                 [{"name": "increase", "vector": [1], "test_kind": "one_sample",
                   "tests": "mean GM change > 0 in treated animals"},
                  {"name": "decrease", "vector": [-1], "test_kind": "one_sample",
                   "tests": "mean GM change < 0 in treated animals"}],
                 rows=rows, groups={"treated": n},
                 data={"file": "all_GM_change.nii.gz",
                       "meaning": "each treated animal's synthetic GM change, later minus earlier"},
                 summary="Does GM change within treated animals? (synthetic)")
    record = read_design_record(out)

    offset = rng.standard_normal(n)
    data = 0.05 * (rng.standard_normal(shape + (n,)) + offset - offset.mean())
    data[blob] += 0.1
    data[~brain] = 0
    data = data.astype(np.float32)
    data_path = _save(work / "all_GM.nii.gz", data, aff)
    t = _one_sample_t(data.astype(float))
    corrp1, p1 = np.full(shape, 0.4), np.full(shape, 0.5)
    corrp1[blob], p1[blob] = 0.99, 0.998
    rd = out / "randomise_GM"
    _write_maps(rd, aff, brain, [(t, corrp1, p1), (-t, np.full(shape, 0.2), np.full(shape, 0.3))])
    mask_path = _save(work / "brain_mask.nii.gz", brain, aff, np.uint8)
    tests, clusters = read_randomise(rd, data_path, out / "design.mat", mask_path,
                                     atlas=Atlas(parc, names, hemi), cluster_on="fwe", alpha=0.05,
                                     min_cluster_size=10, labels={"metric": "GM"})
    write_readout_results(
        out, tests, clusters, analysis_id="vbm/demo_change", title="VBM: GM change (synthetic)",
        description=record["summary"], analysis_type="vbm", modality="anat",
        measure_column="metric", measures=["GM"], run_dirs={"GM": rd},
        n_permutations=5000, alpha=0.05, mask_name="brain mask", space="SIGMA",
        inference="3-D TFCE", role="exploratory", design_record=record, started=FIXED_TIME,
        inputs=[{"path": "all_GM_change.nii.gz", "role": "GM change (synthetic)"}],
        settings={"n_permutations": 5000, "cluster_threshold": 0.95, "min_cluster_size": 10,
                  "seed": 2026},
        caveats=[CAVEAT], mask=mask_path, strict=True)
    return out


def main() -> int:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    rng = np.random.default_rng(2026)
    with tempfile.TemporaryDirectory() as tmp:
        folders = [tbss(rng, Path(tmp)), vbm(rng, Path(tmp))]
    for f in folders:
        _scrub(f)
    reports = check(ROOT)
    for r in reports:
        print(("OK  " if r.ok else "FAIL"), r.id, r.errors, r.warnings)
    return 0 if len(reports) == 2 and all(r.ok and not r.warnings for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
