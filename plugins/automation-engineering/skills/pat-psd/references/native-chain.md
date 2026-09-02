# The native half: `gv_pipeline`, and the parity contract

`native/` is a C++/CUDA program that receives GigE Vision packets and measures particles in mapped
memory, in process, at frame rate. It is the reference measurement of this rig. Python supervises it
and reads its output through five files.

## The one rule

> **The target hardware must never change the algorithm.** Correctness of the native half is defined
> by parity with the frozen Python oracle in `native/oracle/artifacts/`, never by what compiles or
> runs on a dev box.

This was exercised in earnest by the Orin → Thor port. Moving to CUDA 13.2, `sm_110`, gcc 13.3 and
`-std=c++17` left `make c2-parity` at **0 of 15687 field comparisons differing at 1e-9**.

### The oracle is unreproducible and gitignored

`native/oracle/artifacts/` is 175 MB, excluded from git, and **cannot be regenerated**:
`build_oracle.py`'s writers overwrite unconditionally and need 164 raw rig BMPs (3.2 GB) that are not
shipped, and environment drift makes it non-reproducible anyway.

> If it is lost, "correct" becomes undefinable for this codebase.

The same warning covers `data/labels.db`, `data/runs.db` and `data/exports/` — ignored by git, but
**irreplaceable operator data, not regenerable build output**. `git status` staying clean says nothing
about their safety. They need an off-box copy on a schedule.

## Two compiler flags are load-bearing

`--fmad=false` on the two GPU kernels (`cv_measure_gpu.o`, `cv_segment_gpu.o`) and
`-ffp-contract=off` on the host compiler — the same prohibition for gcc.

Contraction fuses a multiply and an add into one instruction with a single rounding. That changes the
last bit of a level threshold or a basin merge, and **those feed discrete decisions**: the result is a
**different number of particles**, not a rounding difference. Drop either flag and parity fails in a
way that looks like a real algorithmic disagreement.

Two smaller fidelity details in the same spirit, both in `cv_measure.cpp`:

- `kRadToDeg = 180.0 / kPi` and `kDegToRad = kPi / 180.0` are precomputed and **multiplied by**,
  "because CPython precomputes these two constants and multiplies by them; doing the division first
  would round differently in the last bit."
- `py_round` transcribes CPython's `float___round___impl` — C `round()` then ties-to-even — because
  `_core_level`'s `int(np.clip(round(0.05 * n), 1, 9))` depends on it.

## The gates of record

```bash
cd native && make c2-parity        # CPU chain vs the frozen oracle: ALL PASS
cd native && make live-parity      # ObjectStage -- the LIVE path -- vs the oracle
cd native && make gpu-all-parity   # GPU measure + segment kernels (slow)
cd native && make gv-measure-smoke # the file front door opens
```

| Target | What it compares |
|---|---|
| `measure-parity` | `measure_check`: 21 fields × 4053 objects, accuracy + strict, with a quality confusion matrix |
| `segment-parity` | `segment_check`: the whole C2 chain from frozen `coarse_blobs.bin`, order-checked |
| `c2-parity` | both of the above |
| `live-parity` | `segment_check --threads 0` — the **pooled** path `cv_stage.cu` actually runs |
| `gpu-parity` / `gpu-segment-parity` / `gpu-all-parity` | the two `--fmad=false` kernels |
| `gpuseg-transcript-parity` | `oracle/gpuseg_parity.py` — the device code transcribed into Python, run against `particlesizer`. **No compiler, no GPU** — an off-Jetson pre-flight |
| `gv-measure-smoke` | measures oracle frame 1725 through `gv_measure --json`, fails if `n_objects == 0` |

**`live-parity` exists because `c2-parity` does not cover the live path.** `c2-parity` exercises
`cvs::measure_coarse_blob` fed Python's own coarse blobs; it does not cover `cvo::ObjectStage`, which
`cv_stage.cu` runs on every live frame. `segment_check`'s pooled block is gated behind `threads >= 0`
and defaults to `-1`, so the plain invocation skips it. That gap "is why the end-to-end object counts
came out 745/3269 against the oracle's 747/3306."

Two build rules have **no phony runner** — `frontend_check` (C1 vs oracle) and `objects_check`
(labels path == CPU-CCL path). `verify_on_jetson.sh` builds and runs them by hand; `make` alone never
will. `annot_render.cpp` has no Makefile rule at all.

The structural expression of the contract: **`measure_check` and `segment_check` link zero CUDA.**
They are `g++`-only binaries.

## The processing chain

| Stage | Where | What |
|---|---|---|
| **C1** front end | GPU (`cv_frontend.cu`, 11 kernels) | normalize → robust stats → Otsu → mask → GPU 8-connected CCL → padded ROI list + dense labels. Bit-exact vs oracle |
| **C2.1** measure | CPU (`cv_measure.cpp`) or GPU (`cv_measure_gpu.cu`) | `measure_blob` + `apply_gates` per object |
| **C2.2** segment | CPU (`cv_segment.cpp`, `cv_objects.cpp`) or GPU (`cv_segment_gpu.cu`) | `clean_patch`, `local_halfmax_level`, `refine_blob_parts`, `split_touching_blobs`; device ports of EDT, morphological reconstruction, `h_maxima`, watershed, basin saddle/shallow merges |
| C3 tracking | — | **deliberately not started.** Kalman + Hungarian linker → split/merge track DAG → cluster count inference. `CvStage::set_objects_sink()` is the attachment point |

`cv_ndimage.cpp` is 19 exact C++ ports of the scipy/numpy/scikit-image primitives the oracle used —
pure C++, no CUDA, no OS calls, no global state. `cv_measure.cpp` is the one file the plan says is
safe to develop off-target.

### The physical model

> - **Transmittance** `T = I / I_background` (T=1 = open screen, T→0 = opaque particle).
> - **Sub-pixel silhouette edge = local half-max** `(T_bg_local + T_min)/2` (symmetric-PSF argument)
>   → **illumination-invariant** (±20%) and **sub-pixel** sizing. **This is the crux of the method's
>   accuracy.**

`optical_depth = clip(1 − t_min, 0, 1)` — fractional obscuration at the darkest pixel, **not** a log
optical depth. `edge_width_px` is the 20–80% intensity ramp width measured along up to **96 rays**
(61 samples each, ±6 px at 0.2 px steps) normal to the contour, taken at the 25th percentile of valid
rays, then geometrically deconvolved against the ramp the particle's own curvature and motion smear
would produce even in perfect focus. It is **NaN** when the ramp is unmeasurable, and NaN is a
*defocus rejection*, never a pass.

The ~22 tuning constants in `cv_measure.cpp:33-58` carry the header **"Do not touch: every one of
them was fitted on the synthetic accuracy benchmark."**

### The five quality gates, in order

`apply_gates`. **The first failure is the one reported, and an unmeasurable input never passes a gate
silently** — every gate has a NaN arm that rejects.

| # | Verdict | Criterion (shipped default) | Physical reason |
|---|---|---|---|
| 1 | `border` | any bbox edge within `border_margin_px = 2` of the frame | a truncated silhouette is undersized and would mislabel every later gate |
| 2 | `too_small` | `d_eq_px < min_diameter_px = 3.0` | "below a few pixels the blur ramp *is* the particle" |
| 3 | `faint` | `optical_depth < min_optical_depth = 0.35` — i.e. `t_min > 0.65` | too transparent to be a well-focused opaque particle |
| 4 | `defocus` | `edge_width_px > max_edge_width_px = 3.0` | the depth-of-field limit, in software. Size biased **high** |
| 5 | `streaked` | `aspect_ratio > max_aspect_ratio = 6.0` | motion-streaked: `d_minor_px` is still valid, `d_eq_px` is not |

Gate 5 is a warning rather than a hard reject. Reject reasons are sentence-form and name the number
that failed, e.g. `"edge_width_px 4.21 > max_edge_width_px 3: outside the depth of field, size biased
high"`.

Measured on the oracle frames:

| frame | coarse | objects | **ok** | border | too_small | faint | defocus | streaked |
|---|---|---|---|---|---|---|---|---|
| 1725 (busy) | 204 | **3306** | **900** | 14 | 2260 | 32 | 71 | 29 |
| 1696 (sparse) | 338 | **747** | **0** | 1 | 530 | 211 | 5 | 0 |

Frame 1696 produces 747 objects and **zero ok** — every one gated. That is the correctness statement
of the gates at the object level, complementing the frame-level `has_particles` test. And note
`too_small` verdicts are *measured and reported*, not skipped: "Sub-3px specks = KEEP, measure &
report (bit-identical to Python; **no cheap area pre-filter shortcut**)." 2260 of 3306 objects on a
busy frame are `too_small` and still cost full `measure_blob` time — which is why the per-object stage,
not pixels, is the throughput wall.

### The frame-level gate, and the escape hatch

Above the per-object gates sits C1's `has_particles`: `noise_floor = o_bg + max(noise_k*o_sigma, 0.02)`
with `noise_k = 6.0`, and the frame is skipped if `o_max <= noise_floor`. This is the test
`GPUPipeline.obscuration_gate` ports into Python — see [psd-math.md](psd-math.md).

Its failure mode on **dense** targets is documented and matters for calibration work: `o_sigma` is
`p84.13 − p50` of obscuration, which measures *noise* only while particles are sparse enough that the
84th percentile still lands in background. On a calibration dot grid or a heavily laden screen,
p84.13 falls **inside** the particles, so the floor is computed *from the signal* and rises above it —
`thr` near 1.0, `rois` 0, `objs` 0, on a frame where the particles are plainly visible.
`--coarse-method fixed` (calibration targets) and `percentile` (production, illumination-relative)
both `return true` **before** that test and are the way out.

### Exposure discipline

The open screen is saturated at 255 **by design**; particles are shadows. **Expose DOWN**, target
~205/255 (T ≈ 0.8). A uniformly white frame has no obscuration anywhere, so `has_particles = false`
and nothing is detected however long you wait. **A white screen and "nothing is detected" are the same
fault, not two.** `gv_measure` prints that hint itself when `has_particles == false`.

## The file contract

`gv_pipeline` publishes four files and reads one. **All writes are tmp + `rename(2)`**, so a reader
never sees a partial file. `patgv/sources/gvsp.py` is the other end.

| File | Dir | Content |
|---|---|---|
| `gvpreview.pgm` | read | downscaled Mono8 frame, P5 only, `maxv <= 255` |
| `gvstat.txt` | read | `key=value`: `fps`, `gbps`, `exp_us`, `gain`, `compl`/`incompl`, `armed`, `objs`, `rois`, `thr`, `o_bg`, `o_sigma`, `cv_ms`, `cv_skipped`, `q_*` |
| `gvobjs.txt` | read | overlay outlines — a **drawing** list |
| `gvobj2.txt` | read | **complete** per-object measurements (`--objdump`) |
| `gvctl` | write | `exp <us>|auto`, `gain <db>|auto`, `detect toggle` |

### Always accumulate from `gvobj2`, never `gvobjs`

`write_detections` decimates each outline to ≥1 preview pixel between vertices and **drops any object
whose outline collapses below two points** (`if (pts.size() < 4) continue`). At the usual preview
stride of 2 that silently removes particles near the bottom of the size range — precisely the ones a
volume-weighted PSD is least sensitive to but a **number**-weighted one is most sensitive to.
Accumulating a run population from it **biases the distribution high without saying so**.

`gvobjs.txt` also carries `n_total` — how many objects the frame actually had — so a consumer can say
that the drawing list is a drawing list. **The count on screen must come from the measurements.**

A second, deliberate incompleteness: annotations are written on a throttled cadence, not every frame.
The *distribution* stays unbiased (frames are sampled without regard to content) but absolute counts
are of sampled frames. `frames_seen` vs `frames_sampled` in the status keeps the two visible.

### `gvobj2.txt` record layout — 30 fields

Header: `gvobj2 <version> <frame_seq> <n> <um_per_px> <field>...`, then one `o <quality>
<reject_reason> <v>...` line per object.

```
area_px  d_eq_px  d_minor_px  d_major_px  perimeter_px  solidity  circularity
orientation_deg  centroid_x  centroid_y  bbox_x0  bbox_y0  bbox_x1  bbox_y1
t_min  optical_depth  edge_width_px  contrast  d_eq_um  d_minor_um  d_major_um
area_um2  aspect_ratio  touches_border  is_saturated  n_dt_peaks  cluster_hint
t_bg_local  halfmax_level  psf_sigma_px
```

`GVOBJ2_FIELDS` in `gvsp.py` and `kObjdumpFields` in `main.cpp` are the two ends. **The reader matches
fields by name from the file's own header**, so a pipeline built before a field was added still
parses, and a reordering is harmless.

Two tests hold them together, and they are the only thing that can — the C++ half only builds on the
Jetson:

```python
def test_field_list_matches_the_c_writer(self):
    """Guard against the two ends of the contract drifting apart.

    ``GVOBJ2_FIELDS`` in gvsp.py and ``kObjdumpFields`` in native/main.cpp
    describe the same record. The reader matches by name so a *reordering*
    is harmless, but a field added on one side and not the other is a silent
    hole, and nothing else in the test suite would notice -- the C++ half
    only builds on the Jetson.
    """
```

The companion test parses `write_objdump`'s format string and asserts one `%` specifier per field
plus exactly two `%s` — "a mismatch between its format string and its argument list is undefined
behaviour that no Python test could otherwise reach."

### `--objdump` throttling, and why

```cpp
// The complete object dump (--objdump) rides the same sink but needs its own
// throttle, because unlike the overlay it does not depend on contours having
// been traced -- so without a clock of its own it would fire on every frame.
// A busy frame is ~300 objects x ~220 bytes; at 74 fps that is ~5 MB/s of
// file I/O landing on the CV thread, which is precisely the thread the
// lossless-receive guarantee depends on staying unblocked.
```

Interval is `1e9 / preview_fps`; at the shipped `preview_fps: 8` that is **125 ms**, a ~9.25×
reduction to ~0.53 MB/s. There is no separate `--objdump-fps`.

`frame_seq` in the dump header is a **dump counter, not a frame counter** — it increments once per
*written* dump. A reader cannot infer dropped frames from it, which is exactly why `gvsp.py`
distinguishes `frames_seen` from `frames_sampled`.

## Nothing may block the CV thread

The rule, and the mechanism that makes it a hard constraint rather than a preference:

1. The CV thread is the **sole consumer** of `ready_q` and the primary producer into `free_q`.
2. The receiver calls `acquire_free()` on every frame leader; if that fails it enters **discard mode**
   for the whole frame and increments `pool_starved`.
3. `pool_starved != 0` makes the run **not `LOSSLESS`**.

So a CV thread stalled longer than `buffers / fps` converts directly into dropped frames — ~324 ms of
headroom at the shipped `buffers: 24` and 74 fps. `CvStage::process` is synchronous by design
("blocks until the kernel and result read-back finish, so the caller may safely recycle the buffer"),
so every added responsibility is a budget question.

Four layered cost controls:

| Mechanism | Effect |
|---|---|
| **One shared 8 Hz throttle** for preview + overlay | the image and its annotations are the SAME frame; contour tracing happens *only* on overlay frames and only while armed |
| **Drop-to-latest** (`cv_catchup`, default on) | if the ready ring backs up, skip to the newest frame and release the stale ones unprocessed — **counted, never silent**. Turns a CV overrun into a lagging preview rather than a dropping receiver |
| **`--max-roi-px`** | a pathological out-of-focus frame cannot stall the pipe. `0 = off`, and off is the default, "because large particles are real targets and must be measured" |
| **Arm / disarm** | while disarmed, C1 still runs (so preview, `rois`, `o_bg`, `thr` keep updating for focus and exposure setup) but the whole segment+measure stage is skipped |

Disarm exists because of a specific trap: with the detector armed on an out-of-focus or badly lit
scene, every dark speck is a candidate, the per-object stage explodes, and the preview drops to
nothing — "so you cannot see well enough to *fix* the focus." Hence `--start-disarmed`, which the
config ships as `true`.

`set_detect` is the one runtime-mutable knob and the only `std::atomic` in `CvStage`, because the
ctl-file poll runs on the reporting thread while `process()` reads it on the CV thread. `set_annotate`,
`set_max_roi_px`, `enable_gpu_*` and `set_objects_sink` are all **"not thread-safe: set before the CV
thread starts."**

## The GVSP receive path

`recvmmsg` batched receive, order-independent reassembly, coverage + de-dup completeness, block-gap
accounting, `SO_RXQ_OVFL`, core pinning. Frames land in a `cudaHostAllocMapped` zero-copy pool with
two lock-free SPSC rings, so **the GPU reads the same physical bytes the NIC wrote** — no copy.

`--packet-size 8938` (**8966 − 28**), never 8972 and never 9000. `nvethernet` unconditionally reserves
34 bytes per frame for MACsec, so the MTU ceiling is `9000 − 34 = 8966`, and GVSP needs the 28-byte
IP+UDP headers off that. The `SCPS_PKT_SIZE` register's **bit30 is DoNotFragment**, which is why it
must be MTU−28 rather than MTU. See [thor-platform.md](thor-platform.md).

### Three offline modes prove it without a camera

| Flag | What it proves |
|---|---|
| `--selftest` | Reassembly over four synthetic frames: in-order, **reversed (tail first)**, dropped-mid, duplicated-mid. Pass requires `ok==4 && complete==3 && incomplete==1 && dup_packets==1 && pool_starved==0 && block_gaps==0` — the counters are asserted, not just the frames |
| `--cuda-check` | Fill a mapped pool buffer on the CPU, run a kernel on the device alias, assert sum and bright-count match over 1 MiB — i.e. the zero-copy aliasing really aliases |
| `--loadtest` | Full pipeline over loopback at volume; forces `cv_catchup=false` and byte-compares the first frame against a golden dump. Validates buffer conservation over time. **Explicitly not a link ceiling** — "loopback is a memory path, not the NIC" |

Byte-correctness of capture against the trusted Python path is provable: stream `--test-pattern 1`
(deterministic ramp), `--dump`, capture the same with `gige_nosdk.py`, `cmp`. Recorded as
**IDENTICAL** on this camera.

## `gv_measure` — the file front door

`gv_pipeline` is camera-shaped: every one of its inputs arrives as GVSP packets. `gv_measure.cu` is a
**thin shell around the same objects** — `gv::Frontend` then `cvo::ObjectStage` — so a frame measured
through this door and the same frame measured through the camera produce identical numbers, and
`make c2-parity` still governs both. It links the identical `.o` files.

No image codec is linked, on purpose: PNG/TIFF/BMP are decoded by Python (which already has OpenCV
for the PAT engines) and piped in as raw Mono8 rows; a `.raw` file — what the FTP camera actually
delivers — is read directly. `--input -` reads stdin. `--bpp` other than 8 is a hard error.

JSON hygiene: NaN and Inf are not valid JSON literals, so `psf_sigma_px` becomes `null`; numbers are
`%.17g`.

Two diagnostic modes worth knowing:

- **`--diag`** runs `ObjectStage` over all four `(T, mask)` pairings — GPU-computed vs
  CPU-recomputed — to localise a `gv_measure` ↔ `segment_check` difference to C1's GPU output, to
  `segment_check`'s CPU recomputation, or to neither.
- **`--ccl`** runs the CPU-CCL overload instead of the front end's labeling. Same object set by
  construction, so it isolates a labeling-path difference from a C1 difference. **The live pipeline
  uses the default (labels) path.**

## Build mechanics

```bash
# The host has no nvcc. Build in the CUDA 13.2 container; the binaries link
# cudart statically and then run on the host against its driver.
docker run --rm -v "$PWD:/w" -w /w/native --user "$(id -u):$(id -g)" -e HOME=/tmp \
  thor-cuda-probe:local make -j"$(nproc)" all

# after any host -> host copy
cd native && make distclean && make -j$(nproc)
```

`-cudart=static` is why a container-built binary runs on the bare host with nothing installed.

**`make distclean` first, always, after a copy.** A Windows→Linux copy strips the executable bit, and
stale `.o` files can carry mtimes *newer* than their sources — so make would skip recompiling them and
then link two layouts of the same struct together. `distclean` also re-`chmod +x`es the scripts.

`make all` builds `gv_pipeline` and `gv_measure` only. It builds **no validator**; each parity target
builds what it needs on demand.

## Shutdown

One `shutdown_pipeline` lambda invoked on the normal path **and every exception path**, so a mid-run
failure can neither `std::terminate` on a joinable thread nor leave the camera streaming to a dead
port. Order matters: acquisition stops and the stream channel is disabled first, then the receiver
joins, then the ready ring is **drained** before the CV thread is told to stop — so no complete frame
is discarded at shutdown.

Manual recovery for a wedged camera: take control, write `AcquisitionStop (0x10300008) = 1` and
`SCP_HOST_PORT (0x0D00) = 0`.

## The open work, per the tree's own record

- **C2 throughput is the open problem.** 74 fps full-res is a 13.5 ms/frame budget; 160 fps at 2048²
  is 6.25 ms. Neither is met. `live-parity` on 12 threads measured `ccl 78.1 + segment 596.3 +
  measure 463.9 = 1138.3 ms → 0.9 fps` on frame 1725 (CPU path, pre-GPU-offload).
- Two of three named causes are fixed (a redundant CPU CCL, ~90 ms/frame; one frame-spanning coarse
  blob as a serial work item). **Per-object heap churn is open.**
- **Launch skew inside the GPU measure is the remaining big item.** ROI sizes on frame 1725 span 128
  → 947,785 px, and the biggest single object is **47% of all per-object pixel work** (top 3 = 57%).
  The proposal is thread-per-object below ~4096 px plus a cooperative block-per-object kernel above.
- **The camera link is physically down**, and it is the only thing blocking a live number. Everything
  above the physical layer is green. See [thor-platform.md](thor-platform.md).
