---
name: pat-psd
description: Work on the PAT-PSD in-line particle-sizing rig for twin-screw wet granulation - the pat+gv codebase on the Jetson AGX Thor, its two cameras and three acquisition paths and four measurement engines, the frozen-oracle parity contract that defines correctness for the C++/CUDA half, the volume-weighted D10/D50/D90 and Sauter/De Brouckere population statistics, the obscuration gate that stops an empty screen fabricating a PSD, the per-camera calibration and CV gates, the pat/psd MQTT trees, and how it does and does not connect to the TSWG extruder and the Ax Bayesian optimizer in Ignition. Use when reading or authoring anything in pat+gv, when a D-value or span looks wrong, when the camera will not stream or the GVSP link is down, when particles are detected on an empty screen or not detected on a full one, when wiring the rig to the optimizer or the historian, or when asked what a PSD number from this rig actually means.
---

# PAT-PSD: in-line particle sizing

Particle size distribution is the critical quality attribute of a wet granulation. **PAT-PSD** is the
in-line imaging instrument that measures it: a backlit shadowgraphy rig where particles fall past a
saturated screen and are measured as **shadows**, on an NVIDIA Jetson AGX Thor, in real time. The code
is `pat+gv`.

It exists to close a loop. The TSWG line's Bayesian optimizer needs a PSD to optimise against; today
that number is entered by hand.

```
Raw materials ─▶ Feeders ─▶ Twin Screw Granulator ─▶ [PSD PAT] ─▶ Dryer ─▶ NIR ─▶ Historian
                                        │                                            │
                                        └──────── setpoints ◀── Ax Bayesian optimizer ◀┘
```

**What of that is actually built** — establish this before promising anything:

| Link | Status |
|---|---|
| Feeders, granulator, barrel zones, die, pump, TCUs | **real** — Thermo Fisher Process 11 over FINS-UDP + MQTT, in Ignition `TSWG` / prod `Extruder-AP31-4-273` |
| **PSD PAT** | **real as an instrument, not connected.** `pat+gv` measures, publishes on `pat/psd/…`, and nothing in either gateway reads it |
| Continuous dryer | **absent.** Prod has a *filter* dryer (`FD-F3-309-3-1`) — a different unit operation, on a different bench, referencing no TSWG tag |
| NIR / moisture | **absent.** No NIR or moisture sensor, tag or project in either gateway. `FDHum-F3-309-3-1` is a CellKraft *humidifier* — humidity control, not moisture measurement |
| Historian for PSD | **absent.** No table anywhere stores a D-value or a distribution |
| Ax Bayesian optimizer | **real, and fed by hand.** `PSD_D50_um` is a text box an operator types into |

## Run this first

```bash
cd $PATGV && bash tools/thor_setup.sh --diagnose        # read-only: NIC, MTU, sysctls, clocks
cd $PATGV && bash verify_on_jetson.sh --quick           # 13 gates; writes verify_report.txt
cd $PATGV/native && make c2-parity                      # correctness of record vs the frozen oracle
bash $PATGV/tools/lan_doctor.sh                         # read-only: why can't I reach the dashboard
```

> **Paths in this document.** `$PATGV` is a checkout of the `pat+gv` repository; `$DEV` and `$PROD` are
> the `projects/` directories inside an Ignition gateway backup. Set them to wherever you keep yours, or
> put `backups_dir` in `automation.local.yaml`.

The dashboard is on **port 7860** and needs `camera.mode: sources`. It has **no access control at all** —
anyone who can reach the page can arm the detector, change exposure and start runs.

## The rig

**Two acquisition sources, and they are different cameras** — not two transports for one camera. A third
path is not a camera at all.

| Path | Transport | Frames | Measured by |
|---|---|---|---|
| `gvsp` | Lucid ATV245S-M over GVSP on `mgbe0_0` (QSFP28 cage) | never enter Python | the native chain, in process, at frame rate |
| `ftp` | a **different** camera uploading over FTP/SFTP | files on NVMe | any selected engine |
| `watchdog` | none — the filesystem | any directory the operator types | any selected engine |

Four engines: **`gv_native`** (oracle-validated, the only one with photometry and quality gates),
**`pat_cv`** (Otsu + morphology, no extra build step), **`pat_ml`** and **`pat_hybrid`** (UNet — present
and selectable, **not validated measurement paths**; see [references/ml-stack.md](references/ml-stack.md)).

The watchdog exists because the FTP transfer stalls. It is slower by construction — a file read and a
full decode per frame — and that trade was made deliberately.

### The GVSP camera is not streaming, and the reason is physical

**Read `docs/THOR-CAMERA-LINK.md` before touching anything network-related.** The ATV245S-M's
25GBASE-SR optic is **built into the camera** — there is no cage on it and no module to swap — it is
fixed at 25.78125 GBd, and IEEE defines **no autonegotiation for fibre PMDs**. This box's QSFP28 cage is
in **10G mode** and its MACs are `fixed-link` with no PHY. Neither end can negotiate. That is a permanent
`NO-CARRIER` — **and the camera still lights its link LED, because it sees light.** It needs the 25G
reflash plus a QSA28 adapter and a 25GBASE-SR optic.

Everything above the physical layer is proven on this hardware: all four parity gates, the offline GVSP
reassembly selftest, and real frames end-to-end through the FTP source into the run/PSD layer.

**Never infer link state from `speed`.** On `nvethernet` it is echoed from the device tree and reads
10000 with no cable attached. Use `/sys/class/net/<if>/carrier`. `native/tune_net.sh` gets this wrong and
will confidently tune an interface with nothing plugged into it.

## The correctness contract

> **The target hardware must never change the algorithm.** Correctness of the native half is defined by
> parity with the frozen Python oracle in `native/oracle/artifacts/`, never by what compiles or runs on a
> dev box.

The Orin → Thor port exercised this in earnest and it held: moving to CUDA 13.2, `sm_110`, gcc 13.3 and
`-std=c++17` left `make c2-parity` at **0 of 15687 field comparisons differing at 1e-9**.

**Two flags are load-bearing and must never be dropped** — `--fmad=false` on the two GPU kernels, and
`-ffp-contract=off` on the host compiler. Contraction changes the last bit of a level threshold or a
basin merge, and those feed **discrete** decisions: the result is a **different number of particles**,
not a rounding difference.

**The oracle cannot be regenerated.** It is 175 MB, gitignored, and needs 164 raw rig BMPs that are not
shipped. *"If it is lost, 'correct' becomes undefinable for this codebase."* `data/labels.db` and
`data/runs.db` are in the same category — ignored by git, irreplaceable operator data. `git status`
staying clean says nothing about their safety.

The C++/CUDA half **only builds on the Jetson**. Elsewhere you can edit it and the Python contract tests
will catch field drift, but `make` will not run.

## What a number from this rig means

Every diameter is an **equivalent circular diameter** — the circle with the same projected area as the
silhouette. **Not** a sieve size, not a hydrodynamic diameter, and **not what a laser diffractometer
reports.** Comparing against Malvern or Sympatec compares two definitions of "size".

- **D10/D50/D90 are volume-weighted (d³) percentiles**, the pharma convention. `Span = (D90−D10)/D50`.
- **D[3,2]** Sauter and **D[4,3]** De Brouckere come from exact power sums — **no binning error at all**.
- Percentiles are **exact** while the run is under 20000 particles and **binned** (±~0.57%) after. The
  dashboard says which. That distinction matters more than the sub-percent difference.
- **Out-of-range diameters are counted, not clipped** — and they are *included* in the moment means while
  being *excluded* from the percentiles. A 50 mm glare blob leaves D50 alone and dominates `d43`.
- **`quality="ok"` from a PAT engine means "nothing was tested"**, not "passed a gate". `pass_rate = 1.0`
  with `gated = false` means **ungated**.

Full derivations, the analyzer tunables and the store schema:
[references/psd-math.md](references/psd-math.md).

## Invariants that must not break

Each of these is a bug that shipped once and was paid for. They are the reason to read this skill.

1. **Per-source calibration.** `sources.<key>.um_per_pixel` — never one global number. Two cameras.
   **All three ship at `1.0`, which is a placeholder, not a calibration**; at 1.0 every diameter is
   pixels labelled as microns and both size gates move with it.
2. **`analyzer.min_area_um` / `max_area_um` are DIAMETERS in microns**, not areas — converted with
   `π/4·d²`. The names are wrong and kept for compatibility. Reading them as areas is a **1571× error**.
3. **An empty screen must measure zero.** A global Otsu always returns a threshold, so on a
   particle-free backlit frame it splits the sensor noise and reports a population — **226 particles from
   a clean 205-DN screen, 2090 from an over-exposed one**, both past `mqtt.min_particles: 20`.
   `GPUPipeline.obscuration_gate` ports the native test (`o_bg + max(6σ, 0.02)`) and runs on the
   **ORIGINAL grey, before CLAHE**, which destroys the absolute levels it depends on. Backlit only, and
   **the ML path has no equivalent.**
4. **8-bit conversion is a fixed shift, never a per-frame autoscale.** 205 has to mean 205 on every frame
   or the exposure discipline and the obscuration test both stop meaning anything.
5. **Always accumulate populations from `gvobj2`, never `gvobjs`.** The latter is a *drawing* list — it
   drops objects whose outline collapses below two preview pixels, which **biases a PSD high**.
6. **Watershed seeds per blob, not from `0.5 * dist.max()`.** One global level is set by the largest
   particle in the frame, so everything under half its distance peak vanishes — **two thirds of a 6–36 px
   population, biased against the small end.**
7. **Per-source CV gates.** `sources.<key>.analyzer` overrides the global block and travels on
   `Frame.analyzer_params`. Different optics cannot share one set of size and shape limits.
   `PatCvEngine` applies *and restores* them inside its measure lock, so the other source's analyzer is
   never left mutated.
8. **Native-measured frames bypass the engines.** Re-measuring in Python would be the same particles with
   a different ruler.
9. **A picture is not a reading.** `measurements=[]` is not `None`, so a preview-only frame would take
   the native branch and publish a retained all-zero PSD to the live tree.
10. **Feeds are never pooled implicitly.** `combined_stats` refuses across calibrations (different
    instruments) and across engines on one source (double counting). `force=True` overrides deliberately.
11. **Nothing may block the CV thread.** It is what makes the receive lossless; `--objdump` is throttled
    for this reason. A stall longer than `buffers / fps` becomes dropped frames.
12. **The watchdog never moves, renames or deletes a source frame.** The watched directory is the
    operator's data. Its output lives in `<watch_dir>/patgv_output/`, excluded from the scan. The `ftp`
    *source* is the opposite — it owns its drop folder.
13. **A frame is only dequeued once it is stable.** Consume `FolderWatcher` through `get_next_file()`,
    never `queue.get()`. And mark a path `_seen` **only after** it is queued — a dropped path already in
    `_seen` is orphaned for the life of the process.
14. **The blank-frame guard archives, it does not delete.** It is a std heuristic on the operator's only
    copy of a frame and it misfires on sparse frames.
15. **`--packet-size 8938`** (= 8966 − 28), never 8972 and never 9000. `nvethernet` unconditionally
    reserves 34 bytes per frame for MACsec, which is also the whole explanation for the odd MTU 1466.
16. **PAT's MQTT trees are frozen.** `<base>/…` and `<base>/cv/…` keep their exact meaning; new material
    goes under `<base>/src/…` and `<base>/run/…`.
17. **In `camera.mode: sources` the Monitor tab is fed by `_MonitorBridge`**, not `camera_loop` — which is
    not started in that mode. Anything pushing frames must go through the bridge, or the dashboard's
    default tab goes black while the rig is healthy.

## Exposure discipline

The open screen is saturated at 255 **by design**; particles are shadows on it. **Expose DOWN, target
~205/255.** A uniformly white frame has no obscuration anywhere, so `has_particles = false` and nothing
is detected however long you wait.

**A white screen and "nothing is detected" are the same fault, not two.**

## The Ignition side, and the gap

The estate implements the rest of the TSWG line, and the optimizer, without this rig.

| Piece | Where | Reality |
|---|---|---|
| Extruder + feeders + zones + pump + TCUs | dev `TSWG`, prod `Extruder-AP31-4-273`, `…_BO` | **real.** Thermo Fisher Process 11 via FINS-UDP; pump and TCUs over MQTT |
| Bayesian optimizer | prod `Bayesian_Platform`, `BO_Parent`; dev `Bayesian_Platform_Alpha` | **real.** Meta's **Ax / BoTorch**, running *outside* Ignition, driven entirely over MQTT |
| Design space | SQL table `bay_opt` on `SQLServer` | bounds only — **never results, never a PSD** |
| The PSD input | `Page/BO`, a component named `PAT` labelled "PAT Feed" | **an unbound text box with a hardcoded default of `"12"`.** `PSD_D50_um: float(self.getSibling("PAT").props.text)` — so an untouched panel publishes 12 µm as a measurement |
| Run metadata | prod `ExpMetadata` — 28 named queries, keyed `(userid, expid, ver)` | real, and **shares no key with the optimizer**, which tracks `session_name` + `trial_index` in MQTT JSON. Nothing joins them |
| Landing pad for this rig | dev `[MQTT Engine]pat/psd/{heartbeat,metrics}` | provisioned, **String, read-only, and referenced by nothing** |
| Any other particle instrument | prod `[default]PAT/FBRM_from_OPC` (Mettler-Toledo **iC FBRM**, chord length) | real, but on a **different site and a different process** — `SM_DPD_microsphere`, `IRVINE/RD3/2209H`, LAI microspheres. **No TSWG or BO resource references it** |

The optimizer's decision variables are **screw speed (50–300 RPM), liquid feed rate (1–10 mL/min), powder
feed rate (10–50 g/min)**, and its objective is **PSD D50 in the 40–50 µm band**. All three parameters
carry `"tag": null` — nothing is bound to a real tag, in either direction.

**So both ends of the integration are half-built and have never been joined.** `pat+gv` publishes
`pat/psd/d50` as a retained bare float; the dev gateway has two unused `pat/psd/` tags. Closing that gap
is a topic subscription and a binding, not a development project — but do it deliberately, because
`valid=false` must gate it. Details and the exact strings: [references/ignition-bridge.md](references/ignition-bridge.md).

### The metadata the knowledge pack asks for

The TSWG PSD knowledge pack lists eleven "critical metadata" items. **Zero of them exist as a tag, table
column or named query in either gateway.** Here is where each one lives — or does not — in `pat+gv`:

| Item | In `pat+gv` |
|---|---|
| Run ID | `runs.run_id` in `data/runs.db`, and `pat/psd/run/status` |
| Sample ID | **no home** in `pat+gv` — `runs.name`/`notes` is the only free text. The estate *does* have `ExpMetadata` keyed `(userid, expid, ver)`, but the optimizer shares no key with it |
| Camera ID | the `(source, engine)` feed key — `gvsp` vs `ftp` |
| Exposure, gain | `gvstat.txt` `exp_us`/`gain`, live only — **not persisted per frame or per run** |
| Frame rate | `gvstat.txt` `fps`; `count_rate_hz` per series point |
| Calibration version | **not versioned.** `um_per_pixel` is snapshotted into `run_feeds` at start; `combined_stats` refuses to pool across differing values |
| Algorithm version | the `engine` string on every feed. Native correctness is the oracle, which has no version either |
| D10 / D50 / D90 | `run_series` + the retained `pat/psd/run/<source>/<engine>/…` scalars |
| **Fines %** | **not computed anywhere.** Must be derived from `hist_*.csv` or the reservoir sample against a fines cut-off |
| Timestamp | `run_series.t`, `frames.csv` |
| Reference measurement | **no home.** Nothing links a run to a laser-diffraction result |

Two of those gaps are worth raising before anyone plans a validation study: **fines fraction is a stated
objective and is not measured**, and **there is nowhere to record the reference measurement the whole
validation strategy is built on.**

## When something is wrong

| Symptom | Look first at |
|---|---|
| Every D-value implausible by a constant factor | `um_per_pixel` is still the `1.0` placeholder — in all **three** places |
| Particles reported on a visibly empty screen | the obscuration gate: `dark_particles` false? on the ML path? CLAHE running before it? |
| Nothing detected on a visibly full screen | over-exposed — a saturated white frame has no obscuration. Expose **down** to ~205 |
| Nothing detected on a **dense** target (dot grid) | the otsu noise floor computed itself from the signal. Use `coarse_method: fixed` or `percentile` |
| Small particles missing, PSD biased high | accumulating from `gvobjs` instead of `gvobj2` — check `sample_complete` |
| Small particles missing with watershed on | global vs per-blob seeding |
| D50 fine but `d43` absurd | out-of-range blobs: counted in the moments, excluded from the percentiles. Working as designed |
| Camera "connected" but no frames, ever | a stale `gvstat.txt`: `compl` is cumulative and satisfies `compl > 0` forever |
| `NO-CARRIER` while the camera's LED is lit | the 10G/25G link. `docs/THOR-CAMERA-LINK.md`. Not a cable |
| Camera streams nothing at all after a tune | `packet_size` — 8972 exceeds path MTU here; it must be 8938 |
| Frames drop after a reboot | `thor_setup.sh --apply` is **not sticky** and there is no systemd unit for it |
| A dashboard button reports success, nothing moves | `controls_reachable` — the ctl file was written with no process reading it |
| Population counted twice | a re-read `gvobj2`, or `_seen`/`release(forget=…)` on the FTP path |
| Refused to pool two feeds | `combined_stats` — two cameras or two engines. Use `?force=1` only if you mean it |
| Engine selection refused (409) | `gv_native` not built, or torch absent. The reason string says which |
| Deploy a trained model → HTTP 500 | `SameFileError`: `ml.model_path` is `<ml.save_dir>/best.pt` |
| Labeling tab has no images | in `sources` mode nothing writes the label DB — only `run_batch.py` does |
| Dashboard unreachable from the plant | `tools/lan_doctor.sh`. Refused = nothing listening; timeout = a firewall dropping |
| Monitor tab black while Sources stream | `_MonitorBridge`, or `camera.mode` was rewritten to `batch` |

## Standing up a measurement you can defend

1. **Calibrate both cameras.** `sources.gvsp.um_per_pixel`, `sources.ftp.um_per_pixel` **and**
   `watchdog.um_per_pixel` — the last two are the same camera and a third place to get it wrong.
   Stage micrometer or certified beads; `docs/CALIBRATION.md`. Binning changes µm/pixel; cropping does
   not.
2. **Set exposure by the background level, not by eye.** Target ~205/255 on the open screen.
3. **Re-derive the FTP camera's gates.** `engines.native.min_optical_depth` and `max_edge_width_px` still
   carry the particlesizer defaults, fitted for the Lucid's optics.
4. **Set `file_bit_depth`** if the sensor is 12- or 14-bit in a 16-bit container. Left unset it is
   inferred, and a mis-scaled frame is judged blank.
5. **Prove an empty screen measures zero** before trusting a full one. `tools/cv_doctor.py`.
6. **Run the gates**: `verify_on_jetson.sh`. Thirteen steps, exit code = failures.
7. **Start a run before acquiring.** Nothing is recorded otherwise — the Start-run button is the only
   thing that decides whether an experiment is on the record.
8. **Point `runs.export_dir` at the NVMe.** The default is a relative path on a rootfs with ~1 GB free.
9. **Only then publish to a control loop**, and make the consumer hold its last good output whenever
   `valid` is false.

## References

- [references/psd-math.md](references/psd-math.md) — `Measurement`, the D-values and moment means, the analyzer tunables, the obscuration gate, watershed, the run store, `combined_stats`
- [references/native-chain.md](references/native-chain.md) — the oracle and parity gates, the load-bearing flags, C1/C2, the five quality gates, the file contract and `gvobj2` fields, CV-thread budget, build mechanics
- [references/sources-engines.md](references/sources-engines.md) — the three paths, sidecar supervision, file-stability discipline, the engine registry, pipeline routing, the watchdog
- [references/config-reference.md](references/config-reference.md) — every `config.yaml` key with its shipped value and what it controls, plus the environment variables
- [references/api-mqtt.md](references/api-mqtt.md) — the four MQTT trees and the three `valid` formulas, every REST endpoint, the seven dashboard tabs, LAN hosting
- [references/thor-platform.md](references/thor-platform.md) — Jetson AGX Thor facts, the camera-link failure and its fix, `thor_setup.sh`, Docker/GPU, GenICam registers, `verify_on_jetson.sh`, stale docs
- [references/ml-stack.md](references/ml-stack.md) — the UNet path, what is wired and what is inert, and the defects to fix before calling it a measurement
- [references/ignition-bridge.md](references/ignition-bridge.md) — the TSWG and Bayesian projects, the hand-keyed PSD input, the unused `pat/psd` tags, and how to close the loop

Related skills: `mqtt-integration` for the broker and topic layer, `ignition-resources` for authoring the
Perspective and tag side, `sql-historian` for storing PSD results, `estate-map` for orientation,
`pitfalls` for the estate-wide traps, `triage` for faults that are not PSD-specific.
