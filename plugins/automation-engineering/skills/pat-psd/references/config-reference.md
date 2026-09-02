# `config.yaml` — the whole key map

453 lines, loaded by `patgv/config.py:load_config()`, which deep-merges the YAML over `_DEFAULTS`.
**No schema validation and no unknown-key rejection** — a misspelled key is silently ignored, so
compare against this map rather than assuming a setting took effect.

Blocks in file order: `sources` `watchdog` `engines` `runs` `calibration` `analyzer` `model` `ml`
`labeling` `training` `server` `camera` `batch` `mqtt` `keyence`.

There is **no `gpu:` block and no `historian:`/`database:` block.** Persistence is
`runs.db_path`, `labeling.db_path`, `keyence.csv_log_path` and flat CSV exports. GPU access is a
container contract, not config. The only concurrency knob is `engines.native.threads`.

## `camera:` — the mode selector that gates everything

| Key | Value | Controls |
|---|---|---|
| `source` | `/dev/video10` | V4L2 device or file, `camera` mode only |
| `mode` | **`sources`** | see below |
| `folder_dir` | `/home/jace/Desktop/nvme` | pseudo-camera dir, `folder` mode only |

| `camera.mode` | Meaning |
|---|---|
| **`sources`** | **the pat+gv mode** — acquisition is handed to the `sources:` block, both cameras at once |
| `camera` | PAT legacy V4L2/file capture from `camera.source` |
| `folder` | PAT pseudo-camera over `camera.folder_dir` |
| `batch` | **fallback only, not settable explicitly** — any unrecognised value silently becomes this |

`run_server.py` validates against `("camera", "folder", "sources")` and rewrites anything else to
`batch`. **`"sources"` was missing from that tuple**, so the documented `camera.mode: sources` was
silently rewritten to `batch` and sources were registered but never started. If a fresh checkout shows
both cameras configured and neither streaming, check that tuple first.

Two coupled consequences of `sources` mode:

- Neither `camera_loop` nor `batch_monitor` runs, and they are the only two things that call
  `broadcast()`. The Monitor tab — the dashboard's **default landing panel** — is fed by
  `_MonitorBridge` instead. Without it, "the operator's first sight of a perfectly healthy rig is an
  empty black video box and `-- fps`, while the Sources tab shows both cameras streaming."
- `POST /api/backends` answers **409**: the per-backend cv/ml/hybrid switch belongs to PAT's shared
  analyzer, and in `sources` mode each source is measured by exactly one engine.
- Sources are still **registered** in other modes, so `POST /api/pg/source/{key}/start` works; only
  auto-start is mode-gated.

## `sources:` — keys are arbitrary; `kind` is not

Per source: `enabled` (falsy → skipped entirely), `kind` (`gvsp`\|`ftp`\|`folder`, anything else
raises), `um_per_pixel`, `analyzer` (**passed only to `ftp`/`folder`, never to `gvsp`**). Everything
else is handed through to the source.

### `sources.gvsp`

| Key | Value | Unit | Controls |
|---|---|---|---|
| `um_per_pixel` | `1.0` | µm/px | **PLACEHOLDER — CALIBRATE ME** |
| `binary` | `native/gv_pipeline` | path | the sidecar; only builds on the Jetson |
| `manage_process` | `true` | bool | `false` = attach to a hand-started sidecar |
| `restart_on_exit` | `false` | bool | re-spawn after a 1 s sleep |
| `poll_interval_s` | `0.1` | s | contract-file poll cadence |
| `preview_path` | `/tmp/gvpreview.pgm` | path | downscaled Mono8 (read) |
| `status_path` | `/tmp/gvstat.txt` | path | `key=value` telemetry (read) |
| `annot_path` | `/tmp/gvobjs.txt` | path | overlay outlines — a **drawing** list |
| `objdump_path` | `/tmp/gvobj2.txt` | path | **COMPLETE per-object dump. The population accumulates from this** |
| `ctl_path` | `/tmp/gvctl` | path | control file (write) |
| `log_path` | `/tmp/gvrun.log` | path | sidecar stdio |

`sources.gvsp.args:` — CLI flags. 25 keys are recognised; anything else is warned about and dropped.

| Key | Value | Unit | Notes |
|---|---|---|---|
| `cam_ip` | `169.254.174.122` | IPv4 | |
| `host_ip` | `169.254.100.1` | IPv4 | link-local, on the camera lane |
| `iface` | **`mgbe0_0`** | ifname | Thor: was `eth1` (mlx5) on the Orin. Must match the lane with a carrier |
| `packet_size` | **`8938`** | bytes | **MTU − 28, not the MTU.** `8966 − 28`. 8972 silently exceeds path MTU → every GVSP packet dropped → "the camera streams nothing" |
| `width` / `height` | `2048` / `2048` | px | 2048² = 160 fps lossless; full res is 5320×4600 |
| `offset_x` / `offset_y` | `1636` / `1276` | px | ROI origin |
| `limit_bytes` | `0` | B/s | `0` = free-run. **There is a pathological regime near 12 Gb/s on this camera** |
| `buffers` | `24` | count | frame pool depth = the CV thread's stall headroom |
| `recv_core` / `cv_core` | `2` / `4` | CPU id | thread pinning |
| `obj_threads` | `6` | count | object-stage pool |
| `preview_fps` | `8` | fps | **also throttles the objdump write** |
| `preview_width` | `960` | px | |
| `start_disarmed` | `true` | bool | boot with the detector off |
| `exposure` | `auto` | µs \| auto | **expose DOWN until background ~205/255** |
| `gain` | `auto` | dB \| auto | |

Also accepted by code but absent from the YAML: `obj_core`, `fps`, `threshold`, `max_roi_px`,
`extra_args`.

Documented but commented out, and the way out of a stuck detector on a **dense** target:
`coarse_method` (`otsu`\|`fixed`\|`percentile`), `coarse_level` (`0.85`), `noise_k` (`6.0`), `inv_bg`
(flat-field `float32[w*h]` of `1/max(bg,eps)`). See [native-chain.md](native-chain.md) for why the otsu
noise floor inverts on a calibration dot grid.

### `sources.ftp`

| Key | Value | Unit | Controls |
|---|---|---|---|
| `um_per_pixel` | `1.0` | µm/px | **a DIFFERENT camera from gvsp — needs its own** |
| `watch_dir` | `/home/admin/patgv-drop/img` | path | Thor: was `/workspace_zyu/img`. **FolderWatcher silently CREATES a missing dir** |
| `processed_dir` / `error_dir` | `…/img/processed` / `…/img/error` | path | pruned from the scan |
| `patterns` | `["*.raw","*.tif","*.tiff","*.png","*.bmp","*.jpg"]` | globs | case-insensitive; `.raw` is **first** |
| `max_queue_size` | `500` | frames | past this, shed and leave un-`_seen` so a rescan retries |
| `stability_wait_s` | `0.2` | s | SFTP partial-write guard. **Do not lower it to 0** |
| `use_polling` | `null` | tri-state | `null` = auto, which **defaults ON** |
| `rescan_interval_s` | `5.0` | s | full-rescan safety net |
| `recursive` | `true` | bool | |
| `raw_width`/`raw_height`/`raw_bpp` | `2048`/`2048`/`8` | | **a `.raw` carries no header** |
| `skip_blank_frames` | `true` | bool | |
| `blank_std_threshold` | `2.0` | DN std | |
| `blank_action` | `archive` | archive\|delete | **archive** — a frame with fewer than ~four 20-px particles measures under 2.0 |
| `decode` | `true` | bool | `false` = hand `.raw` paths to `gv_measure`, no 20 MB decode into Python |
| `file_bit_depth` | *commented* `12` | bits | **set this on a 12-bit sensor.** Unset = inferred per frame |
| `analyzer:` | *commented* | | per-camera gates: `min_area_um: 4.0`, `max_area_um: 800.0`, `min_circularity: 0.25` |

## `watchdog:`

**Only pre-fills the Watchdog tab's form. Nothing starts on its own** — the operator types the
directory and presses Start. Env override: `PAT_WATCHDOG_DIR`.

| Key | Value | Notes |
|---|---|---|
| `watch_dir` | `/home/admin/patgv-drop/img` | **the same directory as `sources.ftp.watch_dir`** — deliberate, see [sources-engines.md](sources-engines.md) |
| `output_dirname` | `patgv_output` | **excluded from the scan** — cannot re-measure its own output |
| `engine` | `pat_cv` | a **third** selection, separate from `ftp`'s |
| `um_per_pixel` | `1.0` | **the same camera as `sources.ftp` — a third place this must be right** |
| `patterns` / `recursive` | as ftp / `true` | a string is split on `,` or `;` |
| `poll_interval_s` | `1.0` | floored at 0.2 |
| `stability_wait_s` | `1.5` | effective floor is `max(…, 2.0)` |
| `raw_width`/`raw_height`/`raw_bpp` | `2048`/`2048`/`8` | |
| `save_images` / `save_csv` | `true` / `true` | the annotated frame is rendered either way — the Monitor tab and the player need it |
| `image_format` / `image_quality` | `.jpg` / `92` | full-res deliverable |
| `preview_width` / `preview_quality` | `1024` / `82` | browser playback copy |
| `draw_rejected` | `false` | rejects use the **same colour**, so the picture would show more particles than the CSV has rows |
| `skip_blank_frames` | `false` | measure everything; **N=0 is a real answer** |
| `analyzer:` | *commented* | allow-listed and null-filtered |

## `engines:`

`engine_by_source.gvsp: gv_native` — "the sidecar already measured it; anything else would be
measuring the same particles twice." `engine_by_source.ftp: pat_cv`. Changeable live from the
dashboard.

`engines.native:` is **the FTP camera's gates** when `gv_native` measures files:

| Key | Value | Flag | Verdict it drives |
|---|---|---|---|
| `gv_measure_binary` | `native/gv_measure` | | |
| `timeout_s` | `120.0` | | |
| `raw_width`/`raw_height`/`raw_bpp` | `2048`/`2048`/`8` | | |
| `min_area_px` | `3.0` | `--min-area-px` | |
| `roi_pad_px` | `6` | `--roi-pad-px` | |
| `split_touching` | `true` | negated flag if false | |
| `refine_local_halfmax` | `true` | negated flag if false | |
| `reject_border` | `true` | negated flag if false | `border` |
| `min_optical_depth` | `0.35` | `--min-optical-depth` | **`faint`** |
| `max_edge_width_px` | `3.0` | `--max-edge-width-px` | **`defocus`** |
| `min_diameter_px` | `3.0` | `--min-diameter-px` | `too_small` |
| `max_aspect_ratio` | `6.0` | `--max-aspect-ratio` | `streaked` |
| `border_margin_px` | `2` | `--border-margin-px` | `border` |
| `threads` | `0` | | 0 = hardware concurrency |

**These still carry the particlesizer defaults, tuned for the Lucid rig's optics.**
`min_optical_depth` and `max_edge_width_px` must be re-derived for the FTP camera before its numbers
mean anything.

## `runs:`

| Key | Value | Unit | Controls |
|---|---|---|---|
| `db_path` | `data/runs.db` | path | `runs`, `run_feeds`, `run_series`. **No per-particle table** |
| `export_dir` | `data/exports` | path | **must point at the NVMe** — the relative default sits on a rootfs with ~1 GB free |
| `checkpoint_interval_s` | `30.0` | s | accumulator → SQLite, overwritten in place |
| `series_interval_s` | `5.0` | s | trend point **and** MQTT cadence |
| `autostart` | `false` | bool | starts a run at boot with `started_by: autostart` |
| `d_min_um` / `d_max_um` | `0.1` / `10000.0` | µm | histogram edges |
| `n_bins` | `1024` | count | each bin 1.13% wide → **~0.57% worst-case percentile error** |
| `reservoir_size` | `20000` | particles | Algorithm-R reservoir **and the exact→binned crossover** |

`runs.record_frames:` — **off by default: ~0.5–1 GB per hour.** These are the **preview** frames
(1024²), because full-res never enters Python on the gvsp path. Recording *follows* the run and never
starts or stops one.

| Key | Value | Notes |
|---|---|---|
| `enabled` | `false` | |
| `sources` | `[gvsp]` | the watchdog writes its own images |
| `every_n_frames` | `8` | `preview_fps` is 8, so ~1 frame/s |
| `image_quality` | `85` | |
| `max_frames` | `3600` | ~1 h at 1 Hz, then **recording stops and says so** |
| `min_free_mb` | `2048` | never fill the NVMe under `runs.db`; checked every 64 writes |

## `analyzer:` and `calibration:`

`calibration.um_per_pixel: 1.0` is a **legacy global; `sources[].um_per_pixel` wins.** It is the target
of `run_server.py --um-per-pixel`.

Full tunable table with meanings: [psd-math.md](psd-math.md). The two that cause the most damage:

- **`min_area_um: 2.0` and `max_area_um: 2000.0` are DIAMETERS in microns, not areas.** `analyzer.py`
  converts with `π/4·d²`. Reading them as areas is a **1571× mistake** at these values.
- **`dark_particles: true` is what enables the obscuration gate.** Set it false and an empty screen
  will fabricate a population again.

Overridable per source: the seven the config comment lists, **plus `use_watershed`**. The blur and
morphology kernel sizes rebuild their filters on assignment and stay global. `psd_outlier_mad_k: 5.0`
applies to **CV per-frame statistics only** — the run population applies no such filter, because for
the native engine the quality gates already do that job and doing both would reject twice.

## `mqtt:`

| Key | Value | Controls |
|---|---|---|
| `broker` / `port` | `10.72.167.253` / `1883` | env `PAT_BROKER`. **No TLS** |
| `username` / `password` | `admin` / *a short numeric literal* | **the broker password is committed in plaintext in `config.yaml`** — treat it as compromised, rotate it, and move it to an env indirection |
| `enabled` | `true` | `run_server.py --no-mqtt` forces false |
| `base_topic` | `pat/psd` | env `PAT_MQTT_BASE_TOPIC` |
| `feedback_enabled` | `true` | |
| `publish_interval` | `1.0` s | control-loop cadence, and the per-feed throttle |
| `publish_scalars` | `true` | retained bare-float leaves, so a PLC/Ignition/PID reads one topic with **no JSON parsing** |
| `min_particles` | **`20`** | the `valid` gate — see below |
| `stale_after_s` | `10.0` | the freshness half of that gate |
| `keyence_psd_view` | `realtime` | rolling window (PID) vs since-reset (Bayesian optimisation) |
| `heartbeat_interval_s` | `60.0` | `0` disables |
| `heartbeat_topic` | `null` | null → `<base>/heartbeat` |

**`min_particles` gates only the `valid` flag.** It never suppresses a publish, never filters a
particle and never affects a D-value. The consumer contract is: **hold the last good output whenever
`valid` is false rather than chase noise.** Full topic map and the three different `valid` formulas:
[api-mqtt.md](api-mqtt.md).

It is **not** a defence against fabricated particles: a saturated backlit screen can yield 226–2090
false "particles" through a global Otsu, well above 20. The obscuration pre-gate is what prevents that.

## ML, server, training, batch, Keyence

| Key | Value | Notes |
|---|---|---|
| `model.backend` | `cv` | only consumer copies it to an inert `_active_backend` string |
| `ml.model_path` | `data/models/best.pt` | UNet checkpoint, and the deploy target |
| `ml.export_dir` / `ml.save_dir` | `data/exports` / `data/models` | |
| `ml.use_hybrid` / `ml.confidence_threshold` | `false` / `0.5` | **both read nowhere.** The ML threshold is a hardcoded 0.5 |
| `labeling.db_path` | `data/labels.db` | env `PAT_DB_PATH` |
| `training.host` / `port` | `0.0.0.0` / **`7861`** | the separate Training UI process |
| `server.host` / `port` | `0.0.0.0` / **`7860`** | read authoritatively by `lan_doctor.sh` and the installer |
| `server.image_quality` | `75` | preview JPEG quality |
| `batch.*` | mirrors `sources.ftp` | for headless `run_batch.py`; `num_workers: 4`. Env `PAT_WATCH_DIR`, `PAT_PROCESSED_DIR`, `PAT_ERROR_DIR`, `PAT_USE_POLLING` |
| `keyence.enabled` / `host` / `port` | `true` / `192.168.0.10` / `8500` | ASCII result stream from a Keyence controller |
| `keyence.iface` | `null` | **the code default is `"eth1"`, which is actively harmful** — that is the camera link on a different subnet, so the connection could never reach the controller. `null` lets routing pick |
| `keyence.psd_bins` / `history_maxlen` / `cum_maxlen` | `24` / `600` / `100000` | |

## Environment variables

| Var | Overrides |
|---|---|
| `PATGV_GV_PIPELINE` | `sources.gvsp.binary` |
| `PAT_WATCHDOG_DIR` | `watchdog.watch_dir` |
| `PAT_WATCH_DIR` / `PAT_PROCESSED_DIR` / `PAT_ERROR_DIR` | the `batch.*` equivalents |
| `PAT_USE_POLLING` | `sources.ftp.use_polling` / `batch.use_polling` (`0`/`false`/`no` opts into inotify) |
| `PAT_DB_PATH` | `labeling.db_path` |
| `PAT_BROKER` | `mqtt.broker` |
| `PAT_MQTT_BASE_TOPIC` | `mqtt.base_topic` |
| `/etc/default/patgv-server` | site overrides for the systemd unit, without editing the unit the installer overwrites |

## The two calibration values that make everything else meaningless

`sources.gvsp.um_per_pixel`, `sources.ftp.um_per_pixel` and `watchdog.um_per_pixel` all ship at
**`1.0`**, which is a placeholder, not a calibration. At 1.0 every diameter is reported in **pixels
labelled as microns**, every D-value and span is wrong by the same factor, and both size gates move
with it — so the gates reject a different population than intended too.

`verify_on_jetson.sh`'s all-green message says exactly this: *"Next: calibrate both cameras
(`sources.*.um_per_pixel` in config.yaml are 1.0 placeholders)."*

Calibrate against a stage micrometer, certified beads, or a known object; `docs/CALIBRATION.md` has the
procedure. Two coupled facts: **binning changes µm/pixel** (2×2 binning doubles it, so recalibrate),
while **cropping the ROI does not**.

`RunManager.combined_stats` refuses to pool feeds whose `um_per_pixel` differs — including when one is
`None` — with the message `"different instruments"`. That refusal is the only automatic protection
against averaging two cameras' distributions together.
