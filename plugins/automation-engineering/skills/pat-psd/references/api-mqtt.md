# The interfaces: MQTT, REST, dashboard

## MQTT — four topic trees on one base

`mqtt.base_topic` = `pat/psd`. All four publishers share **one broker session**: one connection, one
Last-Will, one reconnect policy (`min_delay=1, max_delay=30`, `keepalive=60`, `connect_async`).

```
pat/psd/…                                  PAT's Keyence stream        FROZEN
pat/psd/cv/…                               PAT's CV batch              FROZEN
pat/psd/src/<source>/<engine>/…            live per-frame PSD          new
pat/psd/run/<source>/<engine>/…            the run population          new
pat/psd/run/status                         run lifecycle, retained     new
```

**PAT's two trees are frozen.** `<base>/…` and `<base>/cv/…` keep their exact meaning; new material
goes under `<base>/src/…` and `<base>/run/…`. That split exists because the Keyence stream owns the
base path and CV owns `<base>/cv`, "so the two feeds never collide on a tag."

`<source>` ∈ `gvsp` `ftp` `watchdog`; `<engine>` ∈ `gv_native` `pat_cv` `pat_ml` `pat_hybrid`. Both are
sanitised (`/ + # space tab` → `_`, empty → `unknown`).

### Retain and QoS

| Publish kind | QoS | Retain |
|---|---|---|
| Scalar leaves (bare floats/ints) | 0 | **true** |
| `…/population`, `run/status` | 0 | **true** |
| `…/feedback` (both trees) | 0 | **false** |
| Legacy throttled `metrics` | 0 | false |
| `<base>/status` online / LWT / shutdown | **1** | **true** |

Retain on the scalars exists so a reconnecting PLC, Ignition tag or PID block reads the last value
immediately, with no JSON parsing. **`feedback` is deliberately not retained** — a stale event payload
would be replayed as if current.

Scalar formatting: `bool → "1"/"0"`, `float → "%.3f"`, else `str(value)`.

### `<base>/src/<source>/<engine>/…` — this frame

`FEED_SCALARS = ("d10","d50","d90","span","mean","count","valid")`, each a retained bare value in µm
(span unitless, count integer). Plus a non-retained `…/feedback` JSON carrying `timestamp, source,
engine, valid, stale, age_s, n, n_detected, primary_cv:"d50_um", psd{…}, elapsed_ms`.

Throttled per `(source, engine)` to `mqtt.publish_interval`, and **skipped entirely when the result is
not ok**.

**Frame percentiles deliberately use PAT's step convention, not interpolation, so an existing PID's tag
does not shift** when this code is deployed. See [psd-math.md](psd-math.md).

### `<base>/run/<source>/<engine>/…` — the accumulated population

`RUN_SCALARS = ("d10","d50","d90","span","mean","d32","d43","n","pass_rate","elapsed_s","valid")`, all
retained. Plus a **retained** `…/population` JSON — the full `PopulationStats` minus the histogram,
plus `timestamp, run_id, active, valid, elapsed_s`.

These use the accumulator's **interpolated** percentiles, and they carry `d32` (Sauter), `d43` (De
Brouckere) and `pass_rate`, which the per-frame tree does not.

Driven by `RunManager` series ticks (`series_interval_s`, 5 s), the checkpoint ticker, and run
start/stop. `pat/psd/run/status` is retained and carries `active, run_id, name, started_at, elapsed_s,
feeds:[{source, engine, n, d50_um}]`.

### `<base>/…` and `<base>/cv/…` — the frozen trees

Both carry the same scalar leaf set (`d10 d50 d90 span mean count valid`) plus `metrics`, `status`,
`heartbeat`, `feedback` and `cumulative`. `<base>/d50` is **the named primary controlled variable**.

`<base>/status` is the only QoS-1 retained topic, and it is a three-state liveness flag:
`{online:true,…}` on connect, `{online:false, reason:"lwt"}` as the broker-published Last-Will, and
`{online:false, reason:"shutdown"}` on a clean exit. **Whole-feed liveness lives here; per-reading
trustworthiness lives in `valid`.** They answer different questions.

The feedback loop publishes with `force=True` even when idle or disconnected, **so `valid=false` is
observable** rather than being absent.

### `valid` is computed three different ways

| Tree | Formula |
|---|---|
| `<base>/…`, `<base>/cv/…` | `connected AND (age_s <= stale_after_s) AND (n >= min_particles)` |
| `<base>/src/…` | `(n >= min_particles) AND ((now − result.timestamp) <= stale_after_s)` — **no `connected` term; a frame in hand is the connection** |
| `<base>/run/…` | `active AND (n >= min_particles)` — **freshness is replaced by "a run is actually running"**; a finished run's D50 is history, not a process variable |

Shipped gates: `min_particles: 20`, `stale_after_s: 10.0`.

**The consumer contract, in one line: hold the last good output whenever `valid` is false.** And
remember `min_particles` is not a defence against fabricated particles — an empty screen can produce
226–2090 of them. The obscuration gate is.

## REST

### Liveness and addressing

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness only: `{status, service, hostname, uptime_s, ws_clients, port}`. Touches no source, engine or DB |
| GET | `/api/lan` | Address survey, memoised 10 s. `addresses[{iface,ip,prefix,role,default_route}]`, `lan_addresses[]`, `urls[]`, `warnings[]`, `reachable`. `role ∈ {lan, camera-link, loopback}` — **only `lan` reaches `urls`** |

**`/healthz` deliberately does not check the camera:** "at the start of a shift 'up, and the camera is
down' is normal, and a health check that cannot distinguish that from 'the server is gone' is worse than
none."

### Websockets

| Path | Purpose |
|---|---|
| `/ws` | Monitor feed: binary JPEG frames + text JSON metrics, `heartbeat=15.0`. Accepts `{"cmd":"reset_history"}`. Slow clients dropped after 2 s and reconnect on their own |
| `/ws/keyence` | Keyence state push every 0.2 s. Accepts `{"cmd":"reset_cumulative"}`. Independent of the image pipeline |

### `/api/pg` — sources, engines, runs

| Method | Path | Notes |
|---|---|---|
| GET | `/api/pg/status` | One-poll dashboard state. **Always 200**, carrying `pg_error` |
| GET | `/api/pg/sources` | 503 if no pipeline |
| POST | `/api/pg/source/{key}/{start\|stop}` | 404 unknown key, 400 unknown action |
| POST | `/api/pg/control/{key}` | `{"command","value"}`, command ∈ `exposure`\|`gain`\|`detect`. **409 when `controls_reachable` is false** |
| GET | `/api/pg/preview/{key}` | Annotated preview JPEG, `Cache-Control: no-store`. 404 before the first frame |
| GET / POST | `/api/pg/recording` | `{"enabled":bool}` → `{enabled, run_id, dir, written, dropped, every_n_frames, max_frames, stopped_reason}`. **Never starts or stops a run** |
| GET | `/api/pg/engines` | `{engines[], selection{}, defaults{}}` |
| POST | `/api/pg/engine` | `{"source","engine"}`. **409 unavailable, with a reason.** Returns a `warning` when a run is active |
| GET | `/api/pg/run` | `?hist=1` includes histograms |
| POST | `/api/pg/run/start` | Snapshots the engine selection and per-source `um_per_pixel` |
| POST | `/api/pg/run/stop` | **409** if no run is active |
| POST | `/api/pg/run/resume` | `{"run_id"}` — reattaches to an interrupted run with its population intact |
| GET | `/api/pg/run/combined` | `?source=&force=`. **409 with `forceable:true`** when pooling is not meaningful |
| GET | `/api/pg/runs` `…/{run_id}` `…/{run_id}/series` | `?limit=50` / 404 unknown / `?source=&engine=&limit=5000` |
| POST | `/api/pg/runs/{run_id}/export` | CSVs into `runs.export_dir` |

**`/api/pg/status` answers 200 even when the pipeline failed to build**, carrying `pg_error`:

> A 503 here would leave the dashboard with nothing to display at precisely the moment the operator
> needs to be told what is missing — which on this rig is usually "gv_pipeline is not built" or
> "watchdog is not installed".

That is the whole layer's posture: "a Jetson that will not serve its own status page is much harder to
debug than one that serves a page saying what is missing."

### `/api/wd` — the directory watchdog

| Method | Path | Notes |
|---|---|---|
| GET | `/api/wd/status` | `?hist=1` default on. Session, dirs, engine, patterns, µm/px, counts, `rate_fps`, `next_idx`, `latest`, `csv{}`, `population` |
| GET | `/api/wd/frames` | `?since=0&limit=2000` + `next_idx` |
| GET | `/api/wd/frame/{idx}` | Annotated frame. `?full=1` full-res; `?s=<session>` opts into `max-age=86400`, else `no-store` |
| POST | `/api/wd/start` | Body is the form. Run off the event loop |
| POST | `/api/wd/stop` | Stops and writes `summary.csv` |
| POST | `/api/wd/flush` | Rewrites `summary.csv`/`histogram.csv` without stopping |
| GET | `/api/wd/browse` | `?path=&patterns=` → dirs and match counts. **Directories only; no root jail** |
| GET | `/api/wd/csv/{particles\|frames\|summary}` | Auto-flushes `summary` if missing; `Content-Disposition: attachment` |

**`/api/wd` uses a different error convention from `/api/pg`**: operator errors answer **200 with
`{"ok": false, "error": …}`** so the dashboard can render the message inline. `/api/pg` uses real status
codes. Do not assume one from the other.

`/api/wd/frame/{idx}` is immutable for a given index and cached hard by the browser — that is what makes
scrubbing backwards through a played-back session instant and free.

### PAT's original surface, labeling and training

`GET /`, `GET|POST /api/params`, `GET|POST /api/backends` (**409 in `sources` mode**),
`GET /api/keyence/status`.

Labeling: `/api/labels/images`, `/image/{id}`, `/image/{id}/file`, `/image/{id}/thumb` (≤512 px
**lossless PNG**, cached, `max-age=86400`), `DELETE /image/{id}`, `/images/delete`, `/particle/{id}`,
`/merge`, `/measurement`, `/stats`, `/export`.

Training: `POST /api/train/start` (409 if running), `GET /api/train/status`, `GET /api/train/history`,
`POST /api/train/deploy/{id}`, `POST /api/model/switch`, `POST /api/label/particle/add`,
`GET /api/label/user_particles/{image_id}`, `POST /api/labels/draw`, `/cluster`, `/guess`.

Two live defects on that surface, both in [ml-stack.md](ml-stack.md): `POST /api/train/deploy/{id}`
raises `SameFileError` → **HTTP 500** in the default configuration, and `POST /api/labels/export`
**writes no files**.

The extended labeling routes live under **separate prefixes on purpose**:

> these MUST NOT live under `/api/labels/particle/<x>` because `/api/labels/particle/{id}` already
> matches any single-segment value for `{id}` → `int("add")` explodes → 500 HTML response → frontend
> `r.json()` throws "Unexpected non-whitespace … at position 4" (the `<!DO` of `<!DOCTYPE html>`).

### No access control, by design

> reachable from the LAN and able to change the rig are the same thing here. Do not expose 7860 beyond
> the plant network, do not port-forward it.

Anyone who can reach the page can arm and disarm the detector, change exposure and gain, start and stop
runs, and edit labels. Bandwidth is per viewer.

## The dashboard

One file, `patgv/server/static/index.html`. Seven tabs:

| Tab | What it is |
|---|---|
| **Monitor** | Default landing panel. The `/ws` live view with CV/ML/Hybrid toggles, per-backend D50/Count/Span cards, fusion-weight bar and histogram. Its badge reports **data arrival**, not socket state |
| **Watchdog** | Point it at a directory: backlog oldest-first then arrivals, played back as a scrubbable video, beside session counters, a log-axis PSD, output paths and CSV downloads |
| **Sources** | The browser replacement for `native/preview_view.py`: one card per source with live preview, engine dropdown, Start/Stop, calibration, telemetry, and for GVSP the exposure ×0.8/×1.25/auto, gain ∓1 dB/auto and Arm/disarm controls |
| **Run** | Owns the experiment. Name, Start/Stop, elapsed, the recorder switch, Export CSV, then one card per feed with twelve population tiles and the `exact`/`binned ±x%` and `gated N% pass`/`ungated` pills. Previous-runs table with per-row resume and export |
| **Camera** | The **Keyence controller result stream** — *not* the Lucid camera. Six KPI tiles and two PSD charts (real-time and cumulative-since-reset) |
| **Labeling** | Human-in-the-loop review of the label DB: thumbnail grid with bulk delete, Confirm All / Reject Rest, `+ Draw`, `Cluster`, `Fill from model`, per-particle merge |
| **Training** | Status/Epoch/Val-IoU/Val-Loss tiles over a 2 s poll, Epochs/LR/Batch inputs, and a Models table whose Deploy hot-reloads the analyzer and the ML engines |

### `_MonitorBridge` — why the default tab would otherwise be black

In `camera.mode: sources` neither `camera_loop` nor `batch_monitor` runs, and **they are the only two
things in the codebase that ever call `broadcast()`**. The bridge fills that gap. Anything that pushes
frames must go through it.

Two properties are load-bearing:

> - **It must never slow a source down.** `on_frame` is called on the source's own thread (the GVSP
>   sidecar reader) or on the event loop (FTP). It encodes a JPEG and hands the send to the loop; it
>   never waits for the send, and it **drops frames rather than queueing** when the browser is slow.
> - **It must not flood.** The GVSP source samples at `preview_fps` but the watchdog and a fast FTP
>   drop can go much quicker, and there is no point pushing more frames than a browser will paint.

Rate-limited to 12 fps. Outlines are burned in **here** rather than in the source, "because the source's
poll thread must not do cv2 work, and this bridge is already rate-limited and already encoding a JPEG."
`_metrics` fills only the keys the Monitor tab actually reads — "inventing a per-backend breakdown the
engines never computed would put numbers on screen that mean nothing." A pat+gv source is measured by
exactly one engine, so that engine takes the "cv" card's place and the other two stay hidden.

### UI rules that encode real failures

Each of these is a bug that shipped once.

- **A hung poll must not present stale numbers as live.** `pgFetch` has a 6 s deadline; without one "a
  hung server leaves `pgBusy` true forever and the panel keeps showing `connected · 74 fps` from the
  last good poll — the worst possible lie on an acquisition dashboard." After 3 failed ticks the banner
  says the values are not live.
- **Error banners go in the panel the operator is looking at.** Everything used to go to the Run
  panel's message div, so `"engine gv_native is not available: gv_measure not built"` was written into
  a hidden element and the Start button on the Sources tab just did nothing.
- **A failed frame must not show the previous picture** — say which frame and why, "rather than leaving
  the previous frame on screen, which would read as 'this frame looked like that'."
- **A canvas in a `display:none` panel has no laid-out size**, so a histogram drawn while the tab was
  hidden went nowhere — and on a folder that has finished being consumed the next frame never arrives.
- **The 1 Hz status poll runs on every tab**, because the Monitor's empty-state text and the toolbar
  lock both come from it. Only the expensive half — rendering source cards, which fetches a preview
  JPEG each — is gated on visibility.
- **A session change must be noticed by a tab that did not press Start**, or a restart leaves the old
  session's frames on screen beside the new session's counters.
- **Log-spaced bins cannot be drawn on a linear axis.** The session population lives on a 1024-bin
  log grid over 0.1–10000 µm, so it cannot go through the linear-axis chart the Keyence data uses.
- **`d_min_um`/`d_max_um`, not `hist_edges_um`,** in the run tiles: the 1 Hz poll strips the histogram,
  so the range used to print as a meaningless `0.00-0 um` every time.
- **`sample_complete` is tri-state.** `null` = nothing measured yet (the detector boots disarmed), which
  is not the same claim as "this build has no `--objdump` and your PSD is biased."
- **`inf` is not JSON.** `stale_s` becomes `null` when no frame has arrived, because `json.dumps` writes
  `Infinity`, which `JSON.parse` rejects — "blanking the entire Sources panel for exactly the state it
  exists to report." A `TestJsonIsActuallyJson` test class exists to hold that.

## LAN hosting

```bash
sudo bash install-lan-service.sh --retire-pat   # PAT+GV takes 7860
sudo bash install-lan-service.sh                # systemd unit + ufw + mDNS
bash tools/lan_doctor.sh                        # read-only: why can't I connect
```

Port **7860**, `patgv-server.service`, a **scoped** ufw rule, and an avahi `_http._tcp` advertisement so
the dashboard appears in network browsers. mDNS matters because the Jetson gets its plant address from
DHCP: "the IP an operator wrote on a sticky note stops working at the next lease. The name does not."

**Port 7860 ownership is the main install hazard.** PAT and pat+gv both defaulted to it, and PAT's
compose service carried `restart: unless-stopped` with `network_mode: host` — so it re-bound the real
host port at every boot **and showed an EMPTY Ports column in `docker ps`**. `--retire-pat` defuses the
policy with `docker update --restart=no` before `docker compose down`. Afterwards, `docker compose up
server` and `patgv-server.service` must never both run.

`RestartPreventExitStatus=2` in the unit: exit 2 is "port 7860 is held by something that is not mine to
kill". Restarting cannot fix that — it just hammers the port and floods the journal with the same
diagnosis. `tools/whoholds7860.sh` names the container, which `docker ps` will not do for a
host-networked one.

**The camera link address is never offered as a URL.** `169.254.100.1` is `role: camera-link` in the
survey and excluded from `urls[]` — a test named `test_the_camera_link_is_never_offered_as_a_url` holds
it. `lan_doctor.sh` delegates the whole address question to `python3 -m patgv.server.lan`, "so the
dashboard, `/api/lan` and this script can never disagree about which address is browsable."

`lan_doctor.sh` is **read-only** and says so: "it prints the fix it would run; it runs nothing… a
diagnostic that changes the system destroys the evidence you called it to look at." It walks six
failures in the order they actually happen: no plant address → server down → who holds the port →
firewall (including `iptables -S INPUT`, because "Docker writes its own chains here; a DROP policy on
INPUT blocks the dashboard even with ufw inactive") → `.local` resolution → does it actually answer
(loopback first, then every LAN address — "different result from loopback means the bind address or the
firewall, not the app"). Section 7 then checks the camera link is untouched, because "LAN work has
exactly one way to break the rig."

Laptop-side, the distinction that identifies the fault: **connection refused = nothing listening;
timeout = a firewall dropping silently.**

## `run_batch.py` — headless

Batch mode over the FTP drop folder only, `num_workers: 4`, **one analyzer per worker** because "a
PSDAnalyzer reuses GPU buffers and a CUDA stream internally, so sharing one across threads would race."

Its DB-insert ordering is interrupt-safety, not style: move to `processed/` **first**, insert **second**,
skip the insert if the move failed.

It publishes on `<base>/cv/…` with the whole `MQTTPublisher` base moved one level down, and it is the
**only** thing that writes rows into the label DB — see [ml-stack.md](ml-stack.md).

When no viewer is connected it fast-forwards past the backlog rather than re-analysing: "don't burn GPU
re-analyzing images nobody is watching (the batch container already analyzed + stored them)."
