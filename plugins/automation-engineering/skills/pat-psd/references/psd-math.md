# The measurement: what a number means

Every diameter this rig reports is an **equivalent circular diameter (ECD)** — the diameter of the
circle with the same projected area as the particle's silhouette. It is not a sieve size, not a
hydrodynamic diameter, and not what a laser diffractometer reports. Comparing to Malvern or Sympatec
means comparing two different definitions of "size".

## `Measurement` — the one record type

`patgv/core/measurement.py`. A **strict superset** of PAT's `Particle` and the native
`cvm::Measurement`. The contract (`measurement.py:15-19`):

> Fields the producing engine did not measure stay `None`, and `None` is never silently coerced to
> `0.0` — a missing optical depth is not an optical depth of zero, and a population report that
> averaged the two would be quietly wrong.

Canonical names follow the **native** spelling, because that half is the one validated to 1e-9
against the frozen oracle. PAT's names survive as **read-only** properties:

| Alias | Canonical | Note |
|---|---|---|
| `equiv_diam_um` | `d_eq_um` | |
| `equiv_diam_px` | `d_eq_px` | |
| `feret_max_um` | `d_major_um` | |
| `feret_min_um` | `d_minor_um` | |
| `bbox_xywh` | `bbox` | `bbox` is `(x0,y0,x1,y1)` **exclusive**; the alias converts to `(x,y,w,h)` |

Read-only on purpose: "having two writable names for one quantity is how they drift apart."
**`to_dict()` uses `dataclasses.asdict`, so none of the aliases appear in JSON** — REST consumers
see canonical names only.

### Which engine produces which field

| Group | Fields | Produced by |
|---|---|---|
| Geometry, px | `area_px`, `d_eq_px`, `perimeter_px` | both |
| Geometry, px | `d_minor_px`, `d_major_px` | **native only** (PAT leaves `0.0`) |
| Geometry, µm | `d_eq_um`, `d_minor_um`, `d_major_um`, `area_um2` | both |
| Shape | `aspect_ratio`, `circularity` | both |
| Shape | `solidity`, `orientation_deg` | **native only** |
| Position | `centroid`, `bbox` | both |
| **Photometry** | `t_min`, `optical_depth`, `edge_width_px`, `contrast`, `t_bg_local`, `halfmax_level`, `psf_sigma_px` | **native only** |
| Verdict | `quality`, `reject_reason` | native verdict; PAT is always `"ok"` |
| Cluster evidence | `touches_border`, `is_saturated`, `n_dt_peaks`, `cluster_hint` | native |
| Outline | `contour` | native only |

`psf_sigma_px` is legitimately **NaN** when the intensity ramp is unmeasurable, and `gv_measure`
writes that as JSON `null`.

### `has_photometry` and `quality` — the honesty pair

```python
@property
def has_photometry(self) -> bool:
    """True when the measuring engine produced the optical fields the
    native quality gates need. False for both PAT engines."""
    return self.optical_depth is not None
```

**`quality == "ok"` from a PAT engine means "nothing was tested", not "passed a gate."** `quality`
defaults to `"ok"`, so the *absence* of a verdict is spelled as a pass. `has_photometry` and
`PopulationStats.gated` are the only things keeping the two distinguishable downstream.

**A trap worth knowing.** The live GVSP path reading `gvobjs.txt` also reports
`has_photometry == False`, because the overlay file carries the *verdict* but not the optical depth
behind it. So a genuinely, natively gated live run can show `gated=False`. Only `gvobj2.txt` and
`gv_measure --json` set it. See [native-chain.md](native-chain.md).

Two asymmetries against the "missing is never 0.0" claim, both real: `d_minor_px`/`d_major_px` are
plain `float = 0.0` and `from_particle` never sets them; and `touches_border`/`is_saturated`/
`n_dt_peaks = 1`/`cluster_hint = 0.0` are non-`Optional`, so a PAT particle silently asserts "one
distance-transform peak, not on border, not saturated" about quantities PAT never measured.

## Population statistics

`patgv/runs/psd.py`. The sizing problem it solves (`psd.py:7-14`): 74 fps × ~300 particles/frame ≈
**22,000 particles/second**; an hour-long run is ~80 million particles, ~640 MB of float64 if you
keep every diameter to sort at the end. So the accumulator is **streaming and O(1) in memory**, via
three complementary structures.

### (1) Exact power sums — the moment means are not approximations

Five compensated (Neumaier) accumulators: `n, Σd, Σd², Σd³, Σd⁴`, plus `Σarea`. Compensation matters
because the `d⁴` sum spans a huge dynamic range — a 1000 µm particle contributes 10¹² next to a
5 µm particle's 625. Two-level summation: numpy pairwise within a frame, then one compensated add per
frame, which keeps the per-particle cost to a histogram increment.

```
mean_um  = Σd / n                                  D[1,0]
std_um   = sqrt( max(0, Σd²/n − mean²) )           population std (÷n, not ÷(n−1))
cv       = std_um / mean_um
d32_um   = Σd³ / Σd²                               Sauter mean D[3,2]
d43_um   = Σd⁴ / Σd³                               De Brouckere mean D[4,3]
total_volume_um3 = (π/6) · Σd³                     ECD-sphere volume
```

`d32` and `d43` are therefore **exact, with no binning error at all**. For any non-degenerate
distribution `mean_um < d32_um < d43_um`, and a test asserts it.

### (2) Log-spaced histogram — where percentiles come from

1024 bins over 0.1–10000 µm. Each bin is a factor of `10^(5/1024) = 1.011307` wide, i.e. **1.13%**,
so a percentile read off it is within **~0.57%** of the true value (`bin_resolution_pct`, reported
alongside every result). Two parallel arrays: `_count` (number mass) and `_vol` (`Σd³` per bin).

### (3) Bounded reservoir — Algorithm R, 20000 elements, seed `0x5EED`

The fixed seed makes a run reproducible. The reservoir has a second job: it is the **exact/binned
crossover**.

```python
@property
def is_exact(self) -> bool:
    return self._n <= self._res_size
```

While `n <= 20000` the reservoir *is* the whole population, so percentiles are computed exactly
(linear interpolation in diameter). Past that, they come off the log histogram (log-linear
interpolation inside the crossing bin) and `percentile_error_pct` becomes `bin_resolution_pct`.
**Nothing jumps at the handover** — both paths score the same particles, because both apply the same
half-open range filter `d_min <= d < d_max`. Only sub-bin resolution changes.

Consequence worth stating to an operator: a genuinely monodisperse sample binned at 1.13% reports a
span of ~0.009 rather than 0. Reporting `exact` vs `binned` matters more than the sub-percent
difference, because it tells you how much to trust a span.

### D10 / D50 / D90 and Span

**Volume-weighted (d³) percentiles, the pharma convention.** Volume weighting pulls every percentile
up; a test asserts `d50_um > d50_n_um`, because if it did not, the d³ weighting is not being applied.
Number-weighted values are also computed and carried as `d10_n_um`, `d50_n_um`, `d90_n_um`.

```
span = (D90 − D10) / D50            guarded: 0.0 when D50 <= 1e-9
```

**Two percentile conventions coexist, deliberately.** The accumulator interpolates. PAT's original
per-frame code uses a **step** read that always lands on an observed diameter and is therefore biased
upward by up to one particle's spacing. `percentile_step()` reproduces it, and the live per-frame
MQTT feed uses it **on purpose** so an existing PID's tag does not shift when this code is deployed.
The interpolated value is the correct one and is the default everywhere else.

### Out-of-range diameters are counted, not clipped

> Anything outside is counted in the under/overflow tallies rather than silently clipped into an edge
> bin, because a clipped outlier corrupts a percentile invisibly.

The split is precise, and it is the single most misread thing in this module:

| Statistic | Includes out-of-range particles? |
|---|---|
| `n`, `count_rate_hz`, `min_um`, `max_um` | **yes** |
| `mean_um`, `std_um`, `cv`, `d32_um`, `d43_um` | **yes** |
| `total_volume_um3`, `total_area_um2` | **yes** |
| `d10/d50/d90` (volume **and** number) | **no** |
| `sample()` / `sample_*.csv` | **yes** — offered to the reservoir before the range test |

So on a frame with two 50 mm glare blobs among 10 µm particles, D50 correctly reads ~10 µm while
`d43_um` is dominated by the blobs. That is not a bug in either number; a clipped 50 mm blob would
have pinned D50 to the top bin instead, invisibly.

Separately: **zero, negative, NaN and infinite diameters are dropped before any tally** — they appear
in neither `n`, `n_rejected`, nor the `quality` breakdown. "A zero/NaN diameter is a defect, not a
datum."

### `gated` and `pass_rate`

```
pass_rate = n_ok / (n_ok + n_rejected)      1.0 when nothing was rejected
gated     = at least one measurement carried a non-None optical_depth
```

`pass_rate == 1.0` with `gated == False` means **ungated**, not "everything passed." The dashboard
renders this as a pill reading `gated N% pass` or `ungated`, and the wording is deliberate: "this
engine computes no photometry and applies no quality gate, so nothing was rejected — that is not the
same as everything passing."

### Three per-frame PSD implementations coexist

Worth knowing before you reconcile two numbers that disagree:

| Where | Percentiles | MAD filter | Notes |
|---|---|---|---|
| `analyzer._compute_psd` | step | **yes**, `k=5.0` | float32; what the live CV tile shows |
| `recorder._stats` | step | no | π hard-coded to 15 digits |
| `psd.PopulationAccumulator` | interpolated | **no** | the run-level population |

The run population applies **no** MAD filter: for the native engine the quality gates already do that
job, and doing both would reject twice.

## Analyzer tunables (the PAT CV path)

`patgv/core/analyzer.py`. Defaults as shipped:

| Parameter | Default | Unit | Meaning |
|---|---|---|---|
| `um_per_pixel` | `1.0` | µm/px | **placeholder — calibrate it** |
| `min_area_um` | `2.0` | **µm DIAMETER** | lower size gate |
| `max_area_um` | `2000.0` | **µm DIAMETER** | upper size gate (2 mm) |
| `min_circularity` | `0.3` | — (`4πA/P²`) | shape floor; irregular *and touching* particles fail |
| `threshold_method` | `otsu` | `otsu\|adaptive\|manual` | binarisation |
| `manual_threshold` | `127` | DN | `manual` only |
| `dark_particles` | `true` | bool | backlit; **also gates whether the obscuration test runs** |
| `blur_ksize` | `5` | px, forced odd | Gaussian — **global, not per-source** |
| `morph_open_ksize` | `3` | px | global |
| `morph_close_ksize` | `5` | px | global |
| `use_watershed` | `false` | bool | split touching particles, ~25 ms on 2048² |
| `history_maxlen` | `10` | frames | `get_smoothed_psd` window |
| `psd_outlier_mad_k` | `5.0` | ×`1.4826·MAD` | **per-frame stats only** |

`clipLimit=2.0, tileGridSize=(8,8)` for CLAHE and `blockSize=51, C=10` for the adaptive threshold are
**hard-coded and not exposed**.

### `min_area_um` / `max_area_um` are DIAMETERS

```python
# min_area_um / max_area_um are DIAMETERS in microns despite the names --
# they are converted to areas here. See the note on them in config.yaml.
px_per_um = 1.0 / self.um_per_pixel
min_area_px = math.pi / 4.0 * (self.min_area_um * px_per_um) ** 2
max_area_px = math.pi / 4.0 * (self.max_area_um * px_per_um) ** 2
```

Reading them as areas is a **1571× mistake** at the shipped values (`π/4·2000² = 3,141,593 µm²` vs a
literal `2000 µm²`). The names are wrong and kept for compatibility. There is additionally a hard
floor `max(4.0, min_area_px)` px², and both bounds **scale with the calibration** — so they behave
completely differently once `um_per_pixel` stops being 1.0.

Gate order per contour, first failure reported: `too_small` → `too_large` → `degenerate`
(`perimeter < 1e-6`) → `circularity`. There is **no zero guard** on `1.0 / self.um_per_pixel`.

## The obscuration gate — why an empty screen measures zero

The problem (`gpu_pipeline.py:121-131`):

> a global Otsu ALWAYS returns a threshold. On a particle-free backlit screen the histogram is
> unimodal sensor noise, and CLAHE has already stretched that noise across the range, so Otsu splits
> the noise in half and the contour finder dutifully reports a whole population: measured on the
> shipped settings, **a clean 205-DN screen with 1 DN of noise yielded 226 "particles" at D50 7.3,
> and an over-exposed 250-DN screen yielded 2090**. `mqtt.min_particles` is 20, so those reach a
> control loop as a real PSD.

The test, ported from the native chain:

```
O    = 1 − g / max(bg_field, 1)               obscuration, UNCLIPPED, per pixel
σ    = max( (P25(O) − P12.5(O)) / 0.4758, 0 ) normal-quantile gap: z(.25)−z(.125)
o_bg = P25(O) + 0.6745·σ                      recentre the quartile on the median
thr  = o_bg + max(6.0·σ, 0.02)                six sigma, or 2% obscuration, whichever is larger
gate = clip(O,0,1) >= thr
```

`bg_field` is a **per-pixel** background field (decimate ×32 by area, dilate, Gaussian blur, upscale)
— not a scalar. Max-pool by area *then* dilate, because particles are dark and a plain average would
drag the field down where they cluster.

Three recorded failure modes, each fixed and each worth not reintroducing:

- **Scalar background instead of a field** — a 10% radial falloff, ordinary on a real backlit rig,
  tripled the floor from **0.053 to 0.160** and silently deleted every particle fainter than that.
- **Estimating σ on the *clipped* obscuration** — σ became identically zero, the floor collapsed to a
  bare 2% = 4.1 DN on a 205 DN screen, and it fabricated **178 particles at 4 DN of noise, 1542 at 8 DN**.
- **Median/MAD estimators** — 41% coverage measured fine while 51% reported ZERO with
  `has_particles=False`.

Fallback: if the gate admits nothing but `max(O) >= 0.25`, the floor drops to the bare 2% and the
result is stamped `"obvious obscuration; noise floor was implausible"`.

### Pipeline order — and where CLAHE sits

```
grayscale → OBSCURATION GATE (on the ORIGINAL grey) → CLAHE → blur
          → threshold → morph open → morph close → mask ∧ gate
```

> Computed on the ORIGINAL grey, before CLAHE, because CLAHE destroys the absolute levels the test
> depends on.

Two exemptions: the gate runs **only when `dark_particles` is true** (for bright-on-dark the
formulation inverts), and it is skipped for regions under `MIN_GATED_PIXELS = 256×256` so the
Labeling tab's ROI re-analysis still gets an answer. Applying the mask after morphology is a no-op on
a frame with real particles — the obscuration floor is far more permissive than the threshold Otsu
picks on a bimodal histogram. "It only bites when the threshold has landed inside the noise, which is
precisely the case worth killing."

**There is no equivalent gate on the ML path.** `MLBackend.segment` never calls `preprocess`.

## 8-bit conversion is a fixed shift

```python
def _to_8bit(self, arr, filepath):
    """uint16 -> uint8 by a FIXED shift for the frame's depth.

    Fixed, not per-frame min/max: an autoscale would make every frame its own
    reference and destroy the absolute grey level that backlit shadowgraphy is
    defined against -- the exposure discipline ("expose down to ~205/255") and
    the obscuration test both depend on 205 meaning 205.
    """
```

12-bit `>>4`, 14-bit `>>6`, 16-bit `>>8`. `file_bit_depth` declares the sensor's real depth; unset,
it is inferred per frame from the data maximum — safe here only because in backlit shadowgraphy the
open screen is bright by design, so the maximum sits near the top of the range on every frame.

Why it matters concretely: `IMREAD_GRAYSCALE` divides by 256 unconditionally, so a correctly-exposed
12-bit screen at 80% of full scale (**3276**) arrives as **grey 12** — nearly black, std ≈ 2, which
trips `blank_std_threshold: 2.0`. With `blank_action: delete` it would then be **deleted**. And
`.raw` is the *first* pattern in both `sources.ftp.patterns` and `watchdog.patterns`, so this was the
likeliest path of all.

One place in the tree contradicts the invariant: `engines/gv_native.py`'s `_as_gray_u8` does a
per-frame `arr * (255.0/max)` autoscale. It is unreachable with uint8 input on the shipped paths, but
do not copy it.

## Watershed seeds per blob, never from the frame

```python
# Seed each blob from ITS OWN distance peak, not from the frame's.
#
# The textbook form of this is `threshold(dist, 0.5 * dist.max(), ...)`, one
# global level for the whole frame. That is wrong for a polydisperse
# population, which is the only kind this project measures: the level is set
# by the largest particle present, so every particle whose own peak falls
# below half of it gets no marker, is swallowed by `unknown`, and disappears
# from the result entirely. On a frame with radii spanning 6-36 px it deleted
# two thirds of the particles -- silently, and biased against the small end,
# which is exactly the bias CLAUDE.md refuses to accept from gvobjs.
```

Mechanically: `dist.max()` is the inscribed radius `R` of the largest blob, so a blob of radius `r`
seeds only if `r >= R/2`. Everything smaller gets an empty sure-foreground region, is flooded from
the background label, and is **deleted — not merged**. The deletion is strictly monotone in size. On
the recorded case (radii 6–36 px, `R/2 = 18`), radii 6, 8, 10 and 12 all vanished.

Two details in the fix: `>=` not `>`, so a 1-px-wide blob whose every pixel is the peak still seeds;
and `connectivity=8` to match how `findContours` later groups pixels. Measured limit: pairs
overlapping by up to ~10% of their diameter separate; beyond that the waist is wider than the seed
level and they stay merged, which is inherent to distance-transform seeding rather than a setting.

## The run store

`patgv/runs/store.py`, SQLite at `data/runs.db`. Four tables: `runs`, `run_feeds`, `run_series`,
`run_meta`. **There is no per-particle table** — at 22,000 particles/second there could not be.

- **`run_feeds`** is a *checkpoint*: the accumulator's fixed-size state (power sums, histogram,
  reservoir BLOB) plus its `um_per_pixel`, overwritten in place every `checkpoint_interval_s` (30 s).
  That is what makes a run survive a service restart with its population intact — `resume(run_id)`
  reloads it rather than starting the statistics over.
- **`run_series`** is a *trend*: one append-only row per feed per `series_interval_s` (5 s) carrying
  14 flattened values. No histogram, no quality dict, no under/overflow counts. It grows monotonically
  at 720 rows/hour/feed and **nothing prunes it**. `get_series` defaults to the **oldest** 5000 points.
- `run_meta.schema_version` is written and **never read**; there is no migration path. `PRAGMA
  foreign_keys` is never set, so `run_feeds`'s declared FK is inert.

`export_csv` writes `summary.csv`, `series.csv`, `sample_<source>_<engine>.csv` and
`hist_<source>_<engine>.csv` per run. The reservoir sample is the exportable raw distribution — "a
uniform sample of every diameter the run saw, which is what a downstream tool needs to recompute a
percentile its own way." Only occupied histogram bins are written, and the volume column is named
`volume_um3_rel` because it is `Σd³` per bin, not `(π/6)Σd³`.

## `combined_stats` — feeds are never pooled implicitly

```python
def combined_stats(self, source=None, force=False):
    """Pool feeds into one population -- only when that is meaningful.

    Refuses across differing calibrations unless `force` is set, because two
    cameras' diameters are not one distribution. Within a single source,
    pooling across engines is also refused: the same particles measured
    twice would be double-counted, which inflates n and every mass-weighted
    statistic.
    """
```

Rules in evaluation order:

1. No feeds match → `None` (not an exception).
2. **Exactly one feed → returned verbatim, before any guard runs.** `force` is irrelevant.
3. Double-counting guard, message `"counted twice"` — fires only when `len(engines) > 1 AND
   len(sources) == 1`. Two engines spread over two sources does **not** trip it.
4. Calibration guard, message `"different instruments"` — fires when the set of `um_per_pixel` values
   has more than one member. `None` counts as a distinct value.
5. `force=True` bypasses guards 3 and 4 only. It does **not** bypass `merge()`'s own bin-grid check,
   which is unconditional.

The API surfaces this as **409 with `forceable: true`**, so the dashboard can offer the override
rather than hiding it.

Run lifecycle states are exactly three: `running`, `stopped`, `aborted`. `start()` stops any active
run first — "two concurrent runs would make 'the population of this experiment' ambiguous, which is
the one thing this class exists to answer."

One quiet consequence: `pipeline.py` only calls `add_frame` when `result.ok and result.measurements`,
so **a genuinely zero-particle frame never reaches the accumulator** and does not increment
`n_frames`. `count_rate_hz` therefore counts only *productive* frames.
