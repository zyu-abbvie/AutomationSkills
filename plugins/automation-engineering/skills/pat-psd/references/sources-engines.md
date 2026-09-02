# Acquisition: three paths, four engines

> Two paths reach this project, and they are genuinely different instruments, not two transports for
> one camera.

A third path, the watchdog, is not a camera at all.

## The three paths

| | `gvsp` | `ftp` | `watchdog` |
|---|---|---|---|
| **Transport** | GVSP/UDP on `mgbe0_0`, received by the C++/CUDA `gv_pipeline` process | **none owned by this code** — an external FTP/SFTP daemon writes files; the only contract is "files appear" | none — the filesystem. FTP, SFTP, rsync, a USB stick, a hand copy |
| **Where frames live** | mapped memory inside `gv_pipeline`. Python only ever sees a downscaled PGM | files on NVMe, decoded into Python by `ImageLoader` | any directory the operator types |
| **`Frame` contents** | `image=None` — the picture rides on `FrameEvent.preview` | `image=` **and** `path=` | `image=` **and** `path=` |
| **Measured by** | nothing in Python. `measures_natively=True`; the pipeline hard-codes `engine="gv_native"` | the registry's choice for `ftp` (default `pat_cv`) | the registry's choice for `watchdog` — a **separate** selection from `ftp` |
| **Operator sees** | Sources tab card + Monitor tab via `_MonitorBridge` | Sources tab card + Monitor tab | its **own** Watchdog tab with a scrubbable video player |
| **Throughput** | up to **74 fps** full-res in process; annotations throttled to `preview_fps: 8` | queue-limited (500); one decode per frame in an executor thread; ~5 s polling notice lag | **disk-and-decode speed** — one scanner, one worker, ~1 s poll |

Because they are different cameras, each carries its own `um_per_pixel` and its own CV gates, and the
run layer keeps their populations apart.

### The watchdog is slower by construction

> Nothing about that depends on a transport. Whatever put the files there — FTP, SFTP, rsync, a USB
> stick, a hand copy — they get measured. The cost is real and was accepted going in: every frame is a
> file read plus a decode, so this runs at disk-and-decode speed rather than at frame rate.

Its single worker is also deliberate: "the dashboard plays the annotated frames back as a video, and a
pool of workers would finish out of order and make that playback jump around in time."

The watchdog exists because the FTP transfer stalls. It depends on nothing but the filesystem.

## `gvsp` — supervising the sidecar

`patgv/sources/gvsp.py`, 981 lines. It is a direct replacement for `native/preview_view.py`.

### Process management

The binary path is resolved to an **absolute** path once, in `__init__`. The comment records why:

> `_spawn` passes `cwd=self.workdir` to Popen, and on POSIX the child `chdir()`s there before exec, so
> a relative `argv[0]` would resolve against `native/` rather than the tree root: `native/gv_pipeline`
> became `native/native/gv_pipeline` and the exec failed with ENOENT. The `os.path.exists` check above
> it passed, because that one *is* relative to the server's cwd — so the two disagreed about which
> file they meant.

`build_argv()` always passes all five contract paths explicitly, "so this class and the process it
supervises can never disagree about where the contract lives."

`ARG_FLAGS` is **the authority on which keys are meaningful under `args:`** — 25 flags. Anything else
is *reported*, not silently dropped:

> Anything else under `args:` reaches gv_pipeline through NOTHING. […] a misspelling, or a key that
> belongs one level up (`extra_args` is a SOURCE key, not an `args` key), was previously accepted in
> silence and simply had no effect — the operator sees their setting ignored with no message anywhere.

A bare-string `extra_args` is `shlex.split` with a warning, because `list("--coarse-method fixed")` is
a list of single **characters**.

Missing binary logs the actionable form: *"gv_pipeline not found at %s. It is CUDA/aarch64 and only
builds on the Jetson: `cd native && make`."* `start()` on a source with a live poll thread is **not**
treated as already-started — "returning quietly here made a second start answer 200 ok after the first
had answered 500."

### `stop()` rewinds the contract files, and that is load-bearing

`_clear_contract_files` deletes the four published files *and rewinds their mtimes together*:

> Rewinding without deleting — which is what stop() did for an attached source, where we do not own
> the files and must not remove them — makes the next poll re-read a `gvobj2.txt` this source has
> already consumed and **accumulate that frame's particles into the run population a second time**.

### Status freshness is a precondition, not a detail

```python
# `compl` is a cumulative frame counter on the native side, so any leftover
# gvstat.txt from a run that ever received one frame satisfies `compl > 0`
# forever -- which pinned this source to "connected" over a dead or
# never-spawned pipeline...
fresh = age <= self.STATUS_STALE_AFTER_S
st.connected = fresh and (st.fps > 0 or i("compl") > 0)
```

`STATUS_STALE_AFTER_S = 15.0`, sized against the native **worst case**, not the 1 Hz nominal:
`write_status` does four blocking GVCP register reads, each with 3 retries against a 2.0 s timeout, so
a single unanswered READREG stalls the writer ~6 s and `ACK_PENDING` extends one read further with no
bound.

### The preview is read first, and independently

The PGM is written **outside** every detector guard while the objects sink is **inside** one — so a
disarmed pipeline (`start_disarmed: true`) publishes previews and no object files at all. A preview
cache exists because the native side writes the PGM *before* the sink runs, so a poll landing between
the two would leave the measured frame with no picture.

The codebase records that an earlier comment here was **wrong**, and what believing it cost:

> (An earlier version of this comment said the sidecar "keeps rewriting an empty annotation file the
> whole time" while disarmed. That is false, and believing it is what coupled the preview to this file
> for so long: main.cpp calls `set_annotate(want_annot && due && armed)`, so a disarmed pipeline writes
> NO overlay at all — not an empty one.)

### Reading `gvobj2` must consume the annot cursor too

```python
# Without this the next poll -- which finds no *new* dump, because the reader
# polls faster than the writer throttles -- falls through to the branch below
# and accumulates the same frame a second time from the DRAWING list... At the
# shipped poll_interval_s 0.1 against preview_fps 8 that is about one poll in
# five: a fifth of the recorded population biased high and double counted.
```

`sample_complete` is **tri-state**: `True` = complete objdump; `False` = overlay fallback with a
known-biased sample; `None` = nothing measured yet, so the question has no answer. The dashboard's
copy is explicit that `null` is not the same claim as "this build has no `--objdump` and your PSD is
biased."

### `gvctl` — and why a repeat write still counts

`control()` writes tmp + `os.replace`, and duplicate commands must **not** be suppressed:
"gv_pipeline re-reads the file on every change *including* a repeat of the same text — an earlier
version only re-read on changed content, which made `detect toggle` work exactly once."

`controls_reachable` gates on **status freshness, not frames**:

> `controllable` is a static capability — "this kind of source has exposure and gain". This is the live
> question, and they are different: the GVSP path implements a control as a write to a file another
> process polls, so with that process gone the write succeeds and nothing happens. Answering 200 to
> that is how six dashboard buttons came to report success while the camera never moved.

The API refuses with **409** on that condition and says why. The flag is *published* in the status
payload rather than derived in the browser, "because deriving it in the browser from some other status
field is how the two came to disagree."

## `ftp` — files, and the stability discipline

### A frame is only dequeued once it is stable

```python
# get_next_file(), not queue.get(). The queue carries a path the moment the
# watcher NOTICES it, which for an SFTP upload is while the daemon is still
# writing: reading the queue directly skipped the stability wait entirely, so a
# partial file was decoded and then os.replace'd out from under the writer.
path = await watcher.get_next_file()
```

`get_next_file()` adds four things the raw queue has none of: an existence check (dropping a vanished
path from `_seen` so a re-uploaded filename can be measured again), in-flight dedup, the stability
wait, and a `_seen.discard` on timeout so a rescan can retry.

The stability rule itself: two consecutive `getsize` reads `stability_wait_s` apart must be **equal and
non-zero**, up to 20 attempts. A cheaper pre-guard in the rescan skips zero-byte files outright.

### Mark `_seen` only after the path is actually queued

Two paths mark `_seen` in **opposite orders**, both correct for their situation. The event handler
marks first and un-marks if the put was dropped (it runs on the observer thread, so the put is
dispatched to the loop and its result is only known there). The rescan marks after:

```python
# Mark seen only once it is actually queued, so an overflow drop
# leaves the path for the next rescan instead of orphaning it.
if self._queue.put_nowait_safe(full):
    self._seen.add(full)
```

The invariant both enforce:

> The caller has to know: a dropped path that has already been added to `_seen` is **orphaned for the
> life of the process**, because every later rescan skips it as already-seen. Overflow is meant to shed
> load temporarily, not to lose frames permanently.

`release(forget=…)` is the mirror rule: the file **left** the directory → `forget=True`, so a re-upload
of that name is a new frame; the file is **still there** → `forget=False`, because "since it has
already been measured its particles would be accumulated into the run a second time, then a third,
once per rescan, for as long as the source runs."

### Polling is the default, not the fallback

> Inotify is unreliable across Docker bind mounts in this deployment; polling is slower (~5 s lag) but
> always works. Set `PAT_USE_POLLING=0` to opt back into inotify.

The named failure: "the service starts, logs that the watcher is running, but never sees new files
arriving via SFTP — yet a manual `docker run` from a shell works fine." Three layers of defence: the
PollingObserver, an always-on 5 s rescan, and a startup diagnostic that **warns when `watch_dir` had to
be created**, naming the bind-mount mismatch. That last one is not hypothetical — the FolderWatcher
silently creates a missing `watch_dir`, so the dashboard reported watching it and waited forever.

`start()` also calls `_scan_once` synchronously — that is the FTP path's backlog pass, because "the
event observer only sees files created from now on."

### Disposition happens after the engine

`complete()` is called **by the pipeline**, so a crash mid-measurement leaves the frame where it was
rather than filing it as done. Success → `processed_dir`; failure → `error_dir`; and `_unique_dest`
never overwrites:

> A camera that re-uses filenames — or two runs over one folder — used to land on the same name in
> `processed/`, and `atomic_move` replaced the earlier frame. The frame is the operator's data; it is
> not ours to overwrite.

`atomic_move` is `os.replace` on the same filesystem, and on `EXDEV` stages to `dst + ".part"`, fsyncs,
replaces, unlinks — so an interrupt leaves at worst a stray `*.part`, never a truncated file at the
real destination.

**Every exit path from `_handle_file` must reach `_release`**, "or that filename is blocked for the
life of the process."

### The blank-frame guard archives, it does not delete

```python
# `archive`, not `delete`: the blank test is a std heuristic on the
# operator's only copy of a frame, and it misfires -- any frame carrying
# fewer than roughly four 20-px particles measures under 2.0, so the
# surviving population is concentration-biased, and a mis-scaled 16-bit
# decode used to land every frame under it. Moving to blank/ gets the
# frame out of the way and leaves it recoverable; `delete` does not.
```

The test is `arr.std() < blank_std_threshold` (2.0). "A saturated all-white frame and a dead all-black
one both measure ~0 std. Real particle frames measure in the tens." Note `patgv/config.py` defaults
`blank_action` to `archive` while `run_batch.py` defaults it to `delete` — the two disagree.

### `.raw` geometry is an error, not a guess

> Guessing the geometry is only ever right by luck. A `.raw` has no header, so any `width*height` that
> happens to fit the byte count decodes into a plausible-looking image — and the commonest real
> mismatch is a 16-bit camera read as 8-bit, where the byte count is **exactly double** and a guess
> lands on a wrong-but-fitting shape. The result measures like real data, which is worse than an error.

Both `FtpSource` and the watchdog pass `infer_raw_geometry=False` and get the error. The depth is part
of the answer, not a detail: an earlier version recognised a file as 16-bit by matching `w*h*2` and
then handed back only the shape, leaving the caller to read it at the configured 8 bits — "the top half
of the sensor with every pixel alternating between the low and high byte of adjacent samples, at
exactly the dimensions asked for, with no error."

## The four engines

| Key | Class | Wants | Gated | Display name |
|---|---|---|---|---|
| `pat_cv` | `PatCvEngine` | image | no | PAT CV (Otsu + morphology) |
| `pat_ml` | `PatMlEngine(backend="ml")` | image | no | PAT ML (UNet) |
| `pat_hybrid` | `PatMlEngine(backend="hybrid")` | image | no | PAT hybrid (CV + UNet fusion) |
| `gv_native` | `GvNativeEngine` | either | **yes** | Native particlesizer (oracle-validated) |

Defaults per source:

```python
DEFAULT_ENGINE_BY_SOURCE = {
    "gvsp": "gv_native",      # the sidecar has already done it
    "ftp": "pat_cv",          # runs with no extra build step
    "folder": "pat_cv",
    "camera": "pat_cv",
    # The directory watchdog is a third selection, separate from `ftp` even
    # though both are files on disk: it is usually pointed at a folder by hand
    # while the FTP drop keeps running, and one shared selection would mean
    # changing the engine for one silently changed it for the other.
    "watchdog": "pat_cv",
}
```

`select()` **raises rather than falling back** — "a run whose engine quietly changed is a run whose
population statistics mean something different from what was asked for." The API returns **409 with a
human reason**; availability is a first-class answer, so `GvNativeEngine._probe` distinguishes
not-found from not-executable and the latter names the cause: *"A Windows→Jetson copy strips the
executable bit; run `make distclean` in native/ (it re-chmods)."*

Two engines over the same frames is an **A/B comparison, not a bigger sample**; the run layer refuses
to pool them for exactly that reason. See [psd-math.md](psd-math.md).

## Per-source gates travel with the frame

```python
#: Per-source CV gates, travelling with the frame the same way um_per_pixel
#: does, and for the same reason: these are *different cameras* with
#: different optics, and one global set of size and shape gates cannot serve
#: both. Empty means "use the analyzer as configured".
analyzer_params: Dict[str, Any] = field(default_factory=dict)
```

`PatCvEngine` applies and restores them **inside one lock**:

```python
# There is one PatCvEngine in the registry and it is the default for
# `ftp`, `folder`, `camera` AND `watchdog`, so two sources can be inside
# measure() at once on different threads -- the watchdog's worker thread
# and the aiohttp loop thread that drives the ftp source. They would be
# sharing one PSDAnalyzer, whose calibration this method swaps in place,
# and one GPUPipeline underneath it (one cv2.CLAHE object with mutable
# member buffers, one CUDA stream, one GpuMat reused every frame).
```

> Two sources share this engine and its analyzer: interleaved, one caller's frame is measured with the
> other's ruler — **silently, since the wrong number is a plausible diameter** […] Cost is that the
> ftp source and the watchdog take turns; both are file-based and neither runs at frame rate, and the
> GVSP path does not come through here at all.

The `finally` restore is **inside** the lock, and `frame.um_per_pixel` is forced into the override set
so the ruler is always swapped whether or not the source supplied gates.

### Two allow-lists, and why there are two

```python
PER_FRAME_PARAMS = ("um_per_pixel", "min_area_um", "max_area_um",
                    "min_circularity", "threshold_method",
                    "manual_threshold", "dark_particles", "use_watershed")

#: Of those, the ones the SEGMENTATION backend owns its own copy of. Setting
#: them on the analyzer alone does nothing: CVBackend caches them at
#: construction and segment() reads its own attributes, so these four were
#: silently inert as per-source overrides while still being reported as the
#: gates that produced the numbers.
BACKEND_PARAMS = ("threshold_method", "dark_particles", "manual_threshold",
                  "use_watershed")
```

The blur and morphology kernel sizes are **deliberately excluded** — they rebuild their filters on
assignment and are not safe to swap per frame. The diagnostics report the gates read back **off the
backend**, "so the operator is not guessing which gates produced their numbers."

Note the config comment lists seven overridable keys; the code honours **eight** — `use_watershed` is
in `PER_FRAME_PARAMS` but missing from the comment and from `CLAUDE.md`.

`PatMlEngine` keeps its **own** analyzer, because the backend selection lives on the analyzer and
sharing one with `pat_cv` would mean two engines mutating the same switch.

## Pipeline routing

```python
if event.measurements is not None:
    # Measured natively by the sidecar; nothing for an engine to redo.
    result = EngineResult(measurements=list(event.measurements),
                          engine="gv_native", ...)
else:
    result = self.engines.measure(source_key, frame)
```

The discriminator is `event.measurements is not None` — **not** `source.measures_natively`, which is
only ever reported in `describe()`. **Native-measured frames bypass the engines**; re-measuring in
Python would be the same particles with a different ruler.

### The preview-only guard

Because the discriminator is `is not None`, an **empty list takes the native branch** — and the GVSP
source does emit `measurements=[]` on a preview tick. So there is a second discriminator,
`frame.meta["preview_only"]`:

```python
# A preview-only frame is a picture, not a reading. It exists so the
# operator can see the camera while the detector is idle, and it must
# not enter the measurement path at all: an empty measurement list is
# NOT None, so it would take the native branch below and become an
# EngineResult with ok=True and zero particles. Downstream that reads
# as "we measured this frame and found nothing" -- it would publish a
# retained all-zero PSD to the live MQTT tree, consume that source's
# publish-throttle slot so the next REAL measurement is dropped, and
# count a frame that was never measured.
```

The branch updates `_latest_event` (so the preview endpoint still serves a picture), skips `_latest`,
the counters and the publish entirely, and calls `on_frame` with `result=None` so the Monitor tab keeps
showing the last real reading instead of being blanked to zeros several times a second.

The source side says the same from the other end: "`measurements` is empty rather than absent: nothing
was measured, which is a different claim from 'this sample is missing objects'." And the frame counter
is deliberately **not** advanced — `frames_sampled` counts measured samples, and a live preview is not
one.

The watchdog does **not** go through `Pipeline._handle`; it builds its own `FrameEvent` and always
carries real measurements.

## The watchdog

### Backlog then arrivals, from one loop

There is no separate backlog pass. Ordering comes from an **mtime sort within each scan**, appended to
a `deque` the single worker pops from the left — FIFO across scans.

**The settle test is not skipped for the backlog**, and the comment explains what it cost:

> It used to be skipped entirely for the backlog, on the reasoning that anything already in the
> directory has finished uploading — which is true of a backlog that has been sitting there and false
> of the file the camera happens to be writing at the moment Start is pressed. That one was read
> truncated, measured as if complete, and never looked at again, because it was in `_seen` by then.
>
> Nothing is actually lost by checking: a backlog older than `max(stability_wait_s, 2 s)` — which is
> any real backlog — still passes on the first pass with no added latency.

### It never moves, renames or deletes a source frame

> **Source frames are never moved, renamed or deleted.** The watched directory is the operator's data;
> a watcher that files it away breaks every other tool that was pointed at it.

There is no `os.remove`, `os.rename`, `os.replace` or `shutil.move` anywhere in the module. The `ftp`
*source* is the opposite: it owns its drop folder and does file frames into `processed/`.

### The output tree is excluded from the scan

Everything it writes goes under `<watch_dir>/patgv_output/`, excluded by resolved absolute path, with
`processed`, `error`, `blank`, `__pycache__`, `.git` and dot-directories excluded by name.
`follow_symlinks=False` on both `is_dir` and `is_file`, so a symlink cannot be used to re-enter the
output tree.

**The cross-path version of this hazard is real on this rig.** `sources.ftp.watch_dir` and
`watchdog.watch_dir` ship pointing at the **same directory**, because the docs tell the operator to run
the watchdog over the FTP drop folder when the transfer stalls. The watchdog writes annotated `*.jpg`
there, `*.jpg` is in `sources.ftp.patterns`, and the FTP watcher recurses and **moves** what it
matches. Hence `patgv_output` in `FolderWatcher.SKIP_DIRNAMES`:

> without this exclusion the FTP feed measures the watchdog's drawn overlays as if they were particles
> and then files the watchdog's own deliverable away into `processed/`.

### Output artifacts

```
<watch_dir>/patgv_output/processed/     annotated frames, full resolution
<watch_dir>/patgv_output/_preview/      downscaled JPEGs, for the UI player
<watch_dir>/patgv_output/particles.csv  one row per particle   (append)
<watch_dir>/patgv_output/frames.csv     one row per frame      (append)
<watch_dir>/patgv_output/summary.csv    the population         (rewritten)
<watch_dir>/patgv_output/histogram.csv  undocumented sixth artifact (rewritten)
```

Append vs rewrite is a deliberate split. The CSVs append because "a second watchdog session over the
same directory is more data about the same experiment, not a reason to lose the first one"; the
`session` column keeps them separable. `summary.csv` is rewritten because "it is the answer to 'what
did this session measure', and one row per checkpoint would make a reader guess which one is current."

The session stamp must be **unique, not just descriptive** — it keys the browser's frame-image cache
(frame indices restart at 0) and separates two runs' rows in the appended CSVs. Two sessions inside one
second are not hypothetical: a double-clicked Start does it. Same second gets a `-2`, `-3` suffix.

Output names are flattened collision-free — `sub/frame_001.raw` → `sub__frame_001_raw` — with the
extension folded into the stem so `frame_001.raw` and `frame_001.png` in one folder do not overwrite
each other's annotated output.

The CSV schema is **shared with the live recorder by import**, not by convention: "the same measurement
must produce the same columns whichever path wrote it… Two schemas for one measurement is the kind of
divergence that is invisible until someone concatenates two files a month later."

### The overlay makes exactly one claim

One colour, pure red, no per-particle text:

> This used to be a size ramp (light blue → navy) for accepted particles plus a separate red for
> gate-rejected ones, with each of the largest 60 particles labelled with its diameter. On a real frame
> that reads as a claim the overlay is not making: **two colours look like two classes, and a number
> printed against a particle looks like a per-particle confidence.** The overlay's only job is to show
> WHERE the detector found something. Size lives in the CSV and the PSD, which is where a number can
> carry its units and its uncertainty.

Contour **or** bbox, never both — "a box drawn around an outline reads as two detections." The HUD is
translucent because on a backlit frame the top-left corner is open screen at ~205/255, "and covering it
hides the very thing an operator checks first — whether the background is saturated."

`draw_rejected` defaults `false` because rejects are outlined in the *same* colour, so the picture
would show more particles than `particles.csv` has rows.

### Start ordering is load-bearing

> - **Everything refusable is checked before the running session is touched.** A start that is going
>   to be refused must not be the thing that kills the session that was working.
> - **`stop()` is called outside `self._lock`.** It joins the scanner and the worker, and both of those
>   need `self._lock` to reach their own exit check — so joining while holding it can only ever time
>   out, after which `_stopping.clear()` would revive two live threads against the new session's CSVs.

`_checked_engine` resolves an engine and proves it can run **without selecting it**, so a refused start
leaves the registry's selection as it was. The ruler check refuses a non-finite or non-positive
`um_per_pixel`: "a negative or non-finite value is not a bad measurement, it is a bad *unit*: every
diameter, area and D-value in the session comes out signed or NaN, and nothing downstream can tell that
from real data." `0` and `""` keep their older meaning of "not given" and fall back to 1.0, **which the
session pill displays**, so the placeholder stays visible.

`stop()` reports honestly when a frame is still inside the engine — `gv_native` shells out with a 120 s
timeout, so its counters and player record land but its CSV rows do not: *"stopped while a frame was
still in the engine; that frame's CSV rows were not written"* rather than leaving a one-row discrepancy
to be found in a spreadsheet later.

## Known internal inconsistencies

Places where two artifacts in the tree disagree. Each is a real trap, not a style note.

1. `sources.gvsp.analyzer` is popped by `build_sources` and then **discarded** — `GvspSource` never
   receives it. Harmless (the GVSP path never enters `PatCvEngine`) but silent, unlike the `args:`
   unknown-key warning.
2. `use_watershed` is honoured per source in code but omitted from the overridable-key lists in
   `config.yaml` and `CLAUDE.md`.
3. `histogram.csv` is written and exposed via the API but absent from every artifact list.
4. `FolderWatcher`'s docstring says the rescan defaults to 10 s; the signature and config say 5.0.
5. `max_attempts = 20  # 10 seconds max` is only true at the class default `stability_wait_s=0.5`;
   `FtpSource` passes 0.2, so the real ceiling is ~4 s.
6. `WatchdogProcessor._queue` is an unbounded `deque` and `_seen` is added to unconditionally, whereas
   `FolderWatcher` is bounded at 500 with the whole `_seen`-ordering discipline. The watchdog has no
   overflow path to get wrong, at the cost of unbounded queue memory on a large backlog.
7. `patgv/sources/base.py` still documents the GVSP link as `eth1`; it is `mgbe0_0` on Thor.
8. `keyence.iface` defaults to `"eth1"` in code, which is **actively harmful** — that is the camera
   link on `169.254.100.1`, a different subnet from the controller's `192.168.0.10`, so the connection
   could never reach it. `config.yaml` overrides it to `null`.
