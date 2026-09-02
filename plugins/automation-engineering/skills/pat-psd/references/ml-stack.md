# The ML stack: what it is, and what it is not

The rig ships a UNet segmentation path and a human-in-the-loop labeling UI. **Read this section before
promising anything about it**, because a large part of the surface is wired up in the UI and inert
underneath. Nothing here is a reason not to use the classical CV path or the native chain, which are
the measurement of record.

## The model contributes a mask, and nothing else

**The ML backend produces only a binary foreground mask. Every reported number — ECD, Feret,
circularity, aspect ratio, D50, span — is computed by the classical CV measurement stage from contours
of that mask.**

`analyze_multi` treats every backend identically:

```python
mask = backend.segment(region)
particles = self._measure_particles(mask, offset)
results[key] = self._compute_psd(particles)
```

Consequences that follow directly:

- `_measure_particles` uses `cv2.findContours(..., RETR_EXTERNAL, ...)`, so **holes are discarded and
  touching predictions merge into one particle**. There is no watershed, no distance-transform split and
  no connected-component labelling on the ML path — `use_watershed` is a `CVBackend` parameter only.
- `pat_ml` and `pat_hybrid` are **ungated** and produce **no photometry**, exactly like `pat_cv`. Every
  particle comes back `quality="ok"` with `optical_depth=None`, which means *nothing was tested*.
- **There is no obscuration / empty-frame gate on the ML path.** `GPUPipeline.obscuration_gate` lives in
  `preprocess`, which `MLBackend.segment` never calls. Only the untrained model's output bias stands in
  for it. See [psd-math.md](psd-math.md) for what that gate prevents.

## Inference

`MLSegmentor.predict_mask` — tiled, overlap-added, fully vectorised on the device:

| Property | Value | Configurable |
|---|---|---|
| Patch size / stride | **128 / 64** (50% overlap) | **no** |
| Padding | bottom/right only, `mode='reflect'` | no |
| Inference batch | **64** | no |
| Probability threshold | **0.5**, strict `>` | **no** — `ml.confidence_threshold` is read nowhere |
| Combination | **average of probabilities, then threshold** (soft voting, not mask union) | no |

Interior pixels are covered by 4 windows, edges by 2, corners by 1; `fold` of a ones-tensor gives the
per-pixel multiplicity used as the divisor. The sigmoid is applied per patch, averaged, and only then
compared — so this is soft voting.

`unfold`/`fold` replaced a Python double-loop that extracted ~1000 patches on a 2048² frame and
"dominated runtime (seconds/image)."

A null model returns an **all-zero mask**, which is the failure mode `set_active_backends` exists to keep
off the screen:

> A backend that reports `available == False` is dropped rather than activated. Accepting it would leave
> the UI showing ML as the selected backend while it segments an all-zero mask — indistinguishable, on
> screen, from "the sample really does contain no particles".

## torch is a soft import

```python
# torch is optional here. It is used for exactly one thing -- a CUDA histogram
# in `_compute_psd` -- and that already falls back to `np.histogram`. Importing
# it at module scope made the *classical* CV path unimportable without torch,
# which blocks the pat_cv engine on any host without the JetPack wheel.
```

So the CV path and the native chain work with no torch at all. `ml/train.py` imports torch at module
scope; the tests skip. **torch is not installed on the dev host, so the ML stack is entirely inert
there.**

Loading the ML backend costs "seconds + GPU memory", so `enable_ml=False` skips it entirely for CV-only
callers and per-worker analyzer pools. In `run_batch.py`, `batch.enable_ml` defaults **false** and the
comment names the reason: ML inference was an ~11 s/image bottleneck.

## `LearnedFusion` — the fusion rule, and the disconnected loop

Per-pixel weighted combination of the CV and ML masks with EMA weight updates, weights initialised
`w_cv = w_ml = 0.5`, learning rate `alpha = 0.05`, weight floor `0.05`.

Two documented/implemented mismatches to know before quoting a number:

- The docstring says **"Threshold at 0.5"**; the code computes
  `threshold = 0.3 + 0.2 * min(w_cv, w_ml) / max(total_w, 1e-6)`, which is **0.4 at the shipped equal
  weights** and *falls* to 0.3 as the weights diverge. The inline comment says "higher confidence =
  lower threshold", which inverts the formula's actual behaviour.
- **The online-learning loop is disconnected end to end.** `update_from_feedback` has exactly one
  caller, `PSDAnalyzer.update_fusion_from_label`, which has **no callers at all**. And that method is
  itself a stub: it hardcodes `cv_found=True, ml_found=True` ("Heuristic: assume both found it if it was
  in the result"), so even if it were wired it could not distinguish the backends and the CV:ML *ratio*
  would never change. `save()` and `_save_weights` are unreachable; `data/fusion_weights.json` is never
  created.

Hybrid degrades to CV when ML is unavailable, which is the right default.

## Training

Two entry points that **behave differently**:

| | `run_training.py` (CLI) | dashboard Training tab / `run_training_ui.py` |
|---|---|---|
| Early stopping | **yes** | no |
| Optimizer state in checkpoint | yes | **no — no resume is possible** |
| TorchScript export | yes | **no — state_dict only** |
| Calibration passed through | yes | **no — see D3 below** |
| Port | — | 7861 (standalone) / folded into 7860 |

Defaults from `POST /api/train/start`: `epochs: 50`, `lr: 1e-3`, `batch_size: 16`.

No checkpoint carries architecture metadata, so `MLSegmentor` reconstructs `ParticleUNet()` with
defaults.

**Absent entirely** (verified by grep): AMP, fp16, `GradScaler`, `channels_last`, `cudnn.benchmark`,
TensorRT, ONNX, quantization, `torch.compile`. On a Thor with 122 GiB unified memory the absence of AMP
is a throughput choice rather than a blocker, but do not describe this as an optimised training path.

`patgv/ml/augment.py` (122 lines: Gaussian noise, elastic deformation) has **no importer**, so those
augmentations are absent from real training.

### Deploying a model does not pick it up by itself

`POST /api/train/deploy/{id}` copies the checkpoint to `ml.model_path` and then **hot-reloads** the
analyzer's ML backend *and* the `pat_ml` / `pat_hybrid` engines, returning `refreshed[]`. The engine's
own method says why:

```python
"""Drop the analyzer so the next measure picks up a newly deployed model.
The Training tab calls this after a deploy."""
```

## Labeling

`data/labels.db`, five tables. Thumbnails are **lossless PNG** (≤512 px, cached, written to a temp
sibling then atomically renamed) — "no JPEG artifacts on the processed image"; the annotation view loads
the full-resolution original. The cache never goes stale because "source frames are immutable once
processed."

An empty gallery and a broken database are rendered **differently**:

> An empty gallery with "Confirmed:0 Rejected:0 Auto:0" used to be shown both when the database was
> genuinely empty and when it had failed to open. Those are different problems and the operator could not
> tell them apart.

### A label with a zero diameter must never be written

```javascript
// Only diameters the operator actually typed. setTool('cluster') pre-builds
// two EMPTY inputs, so averaging the raw list wrote a 0.00 um measurement
// into the label store as if it had been measured -- a confirmed label with
// a diameter of zero, which then trains on it.
```

The cluster path has both a client guard and server-side `> 0` checks. **The draw path does not** — see
D10 below.

## What does not exist, or is a stub

The absence is load-bearing information. Stated precisely so nobody plans around a phantom.

**Never called / unreachable**

1. `LearnedFusion.update_from_feedback` — the online-learning loop, disconnected end to end.
2. `LearnedFusion.save()` / `_save_weights` — unreachable.
3. `PSDAnalyzer.update_fusion_from_label` — no callers, and a stub if it had any.
4. `HybridAnalyzer` (union / intersection / ml_only / cv_only) — never instantiated.
5. `patgv/ml/augment.py` — no importer.
6. `create_initial_model.py` — referenced by no code, doc, script or Dockerfile; not in the image.

**Declared and unused**

7. `particles.contour_json` — declared, never written, never read. **No per-particle outline is ever
   persisted**, which is why the exporter can only draw bounding-box masks.
8. `ml.confidence_threshold` — read nowhere; the threshold is a hardcoded 0.5.
9. `ml.use_hybrid` — read nowhere.
10. `model.backend` — copied into an inert `_active_backend` string.
11. `LabeledParticle` dataclass — no constructor call anywhere.

**Stub / no-op endpoints**

12. `POST /api/model/switch` sets a config string and logs. **It never calls `set_active_backends`.** The
    four buttons in the standalone Training UI's Model tab do nothing.
13. `GET /api/model/backends` advertises `hybrid_union` / `hybrid_intersection`, which are **not valid
    backend keys** — the analyzer registry has `{cv, ml, hybrid}`.
14. **`POST /api/labels/export` writes no files.** It returns rows as JSON. Despite the name it is not
    the exporter, and `run_training.py --export-first`'s help text ("Export labeled data before
    training") has no wiring to it.

**Missing capability**

15. No instance separation on the ML path — `RETR_EXTERNAL` contours only.
16. No obscuration / empty-frame gate on the ML path.
17. No test coverage for `ml/train.py`, `ml/inference.py`, `ml/augment.py`, `labeling/export.py`,
    `training/trainer.py`, or `LearnedFusion`.
18. **Nothing populates the label DB in `sources` mode.** Only `run_batch.py` writes `images`/`particles`
    rows; neither the `sources` pipeline nor the watchdog does. `config.yaml` ships
    `camera.mode: sources` — so on the shipped configuration the Labeling tab has no input.

**Current on-disk state of this checkout**

19. `data/models/` **does not exist**; there is no `best.pt`.
20. `data/labels.db` exists with all five tables and **0 rows in every table**.
21. `data/exports/images/` and `masks/` exist and are **empty**; there is no `labels.json`.

## Defects, with the code

Reproducible from the quoted lines. Each is stated as a fact about the code.

**D1 — `POST /api/train/deploy/{id}` raises `SameFileError` → HTTP 500 in the default configuration.**
The trainer registers `data/models/best.pt`; the handler does
`shutil.copy2(target["path"], config["ml"]["model_path"])`; and `ml.model_path` is
`data/models/best.pt` while `ml.save_dir` is `data/models`. Source and destination are the same inode,
and `shutil.copyfile` begins `if _samefile(src, dst): raise SameFileError`. Uncaught. **Deploy only works
if `ml.model_path` is moved off `<ml.save_dir>/best.pt`.**

**D2 — the ML tooltip always names the wrong path.** `MLBackend` stores `self._model_path` and exposes no
`model_path`, so `getattr(backend, "model_path", "data/models/best.pt")` always returns the default
literal — including for the `"__ml_disabled__"` sentinel.

**D3 — the dashboard Trainer silently loses calibration.** The dashboard passes the *full* config to
`Trainer`, which reads *flat* keys, so `config.get("um_per_pixel", 1.0)` yields **1.0**, ignoring
`calibration.um_per_pixel`. Every dashboard-initiated training run therefore records the wrong
`um_per_pixel` provenance in `labels.json`. `training/app.py` builds the correct flat dict; the two entry
points disagree.

**D4 — `LabelStore` cannot be constructed with a dirname-less path.**
`os.makedirs(os.path.dirname(db_path), exist_ok=True)` raises `FileNotFoundError` for `"labels.db"` or
`":memory:"` — and `tests/conftest.py`'s `sample_config` ships `":memory:"`.

**D5 — the write lock covers 2 of 10 writers.** The docstring claims serialisation across batch worker
threads; only `add_image` and `update_image_path` take the lock. Every other mutator shares the same
`sqlite3` connection unlocked.

**D6 — the exporter and the REST handlers disagree on how to find an image.** `export.py` uses
`source_path` alone; every REST route uses `_resolve_image_path` with a six-directory fallback. **An
image the operator can label may be silently skipped at export.** The codebase already fixed exactly this
for `handle_guess_particle`:

> A private two-candidate list here meant an image the annotation view displayed happily still 404'd the
> moment the operator drew a box on it.

**D7 — training masks are bounding boxes, and co-located particles are labeled background.** One
threshold patch per particle bbox. Not a coding defect — the comment says `simple threshold around bbox`
— but **the single most consequential property of the stack: the model cannot learn shape, and dense
fields generate contradictory pixel labels.**

**D8 — unconfirmed CV output is training data by default.** The exporter hardcodes
`label_types=["confirmed", "auto"]`, and `'auto'` is the default for everything `run_batch.py` inserts.
**Without operator rejection, the ML model is trained to reproduce the CV backend.**

**D9 — `'cluster'` labels never reach training.** `add_cluster_particles` writes `label_type='cluster'`;
the exporter selects only `confirmed`/`auto`. The cluster tool's output contributes to PSD statistics but
not to the model.

**D10 — a drawn particle can enter training at 0 µm with fabricated shape.** The draw handler coerces an
unparseable diameter to `0.0` and inserts it as `label_type="confirmed"` with `circularity = 1.0`,
`perimeter_px = 0.0`, and `feret_max = feret_min = equiv_diam`. The cluster path has an explicit `> 0`
guard; **the draw path does not.**

**D11 — the fusion comment inverts its own formula** (above).

**D12 — `multi.results.get(self.backend) or multi.primary`** — `PSDResult` has no `__bool__`, so it is
always truthy and the `or` branch is dead. An empty result for the requested backend is returned as a
*successful zero-detection measurement* rather than falling through.

**D13 — validation IoU scores a correct empty prediction as 0.** `intersection / (union + 1e-6)` with
both terms zero → 0.0, averaged into `val_iou` — and `val_iou` is what the Training tab shows the operator
as model quality.

## If you are asked to make the ML path trustworthy

In dependency order, because several of these block the others:

1. **Fix D1** — move `ml.model_path` off `<ml.save_dir>/best.pt`. Nothing can be deployed until this
   works.
2. **Give the label DB an input in `sources` mode** (item 18). Today only `run_batch.py` writes rows, and
   the shipped mode is `sources`, so there is nothing to label.
3. **Fix D8** — stop exporting `auto` labels unreviewed, or the model learns to imitate `pat_cv` and
   adds nothing.
4. **Persist `contour_json`** (item 7) and export **real masks** instead of bbox patches (D7). Until then
   the model cannot learn shape, which is most of what an ML segmenter is for.
5. **Add an empty-frame gate to the ML path** (item 16), or `pat_ml` will fabricate a population on a
   saturated screen exactly as `pat_cv` did before its gate existed.
6. **Fix D3** so training records the calibration it actually used.
7. **Add instance separation** (item 15) — `RETR_EXTERNAL` merges touching predictions, which biases a
   PSD low in count and high in size, in a dense field, silently.

Until at least 1–4 are done, `pat_ml` and `pat_hybrid` are best described as *present and selectable*,
not as *validated measurement paths*. `gv_native` is the oracle-validated one; `pat_cv` is the
no-extra-build fallback.
