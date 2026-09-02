# The platform: Jetson AGX Thor, and why the camera does not link

## Platform facts

| | |
|---|---|
| Board | **Jetson AGX Thor** devkit |
| BSP | **JetPack 7 / L4T R39.2.1** (flashed 7.2.1) |
| OS / kernel | **Ubuntu 24.04** (noble), kernel **6.8** |
| Python | **3.12** |
| CUDA | **13.2**, GPU arch **`sm_110`** (compute capability 11.0) |
| Host compiler | **gcc 13.3**, `-std=c++17` |
| Cores / memory | **14** / **122 GiB unified LPDDR5** |
| Camera NICs | 4× `nvethernet` MGBE MACs `mgbe0_0..mgbe3_0` on the QSFP28 cage — each **fixed-link 10000 Mb/s, no autoneg**, maxmtu 9000 |
| RJ45 | 1× Realtek RTL8126 5GbE = `enP2p1s0`, maxmtu 9194 |
| Management path | **Wi-Fi `wlP1p1s0` — the only one.** Protected by name in the tuner |
| Usable jumbo MTU | **8966** (9000 − 34 MACsec) |
| Default MTU as shipped | **1466** (1500 − 34) |
| GVSP packet size | **8938** (8966 − 28) |
| Host CUDA toolkit | **none** — `nvcc` lives only in a container |
| Host driver | `libcuda.so.1` → **`/opt/nvidia/l4t-gpu-libs/openrm`** |
| `sudo -n` | **fails** — every root action needs an interactive password |
| Other containers | **eleven unrelated containers live on this host** |
| Ports | dashboard **7860**, training UI **7861** |
| Test suite | **362 tests** green on this box |

**Not** Orin / `sm_87` / CUDA 11.4 / Python 3.8. A great deal of the tree still says otherwise.

### Stale claims still in the repo

`CLAUDE.md` is the canonical correction and says so: *"anything in the docs still saying that is
stale."* The main offenders, so you do not act on one:

| Location | Stale claim | Actual |
|---|---|---|
| `README.md`, `HANDOFF.md`, `TRANSFER.md`, `native/PLAN.md`, `native/PERFORMANCE.md`, `START_HERE.md`, `RUN-ON-JETSON.md` | "the Orin", CUDA 11.4, gcc 9.4, `sm_87`, 12 cores, `-std=c++14` | Thor, 13.2, 13.3, `sm_110`, 14, C++17 |
| `README.md`, `docs/FTP-SETUP.md`, `docs/LAN-HOSTING.md`, `docs/CV-TUNING.md`, `tools/lan_doctor.sh` | `eth1` / mlx5 / "25 GbE" as the camera link | `mgbe0_0`, nvethernet, 10G-mode and **down** |
| `README.md`, `docs/RUNNING-EXPERIMENTS.md`, `docs/WATCHDOG.md`, `HANDOFF.md` | `sudo bash native/tune_net.sh --iface eth1` | `sudo bash tools/thor_setup.sh --apply` |
| **`HANDOFF.md`**, `docs/CALIBRATION.md` | **`--packet-size 8972`** | **8938** |
| `docs/*`, `patgv/config.py` | `/workspace_zyu/img`, `/home/jace/Desktop/nvme` | `/home/admin/patgv-drop/img` |
| `deploy/patgv-server.service` | "the **mlx5** NIC can enumerate a moment late"; "`/usr/bin/python3` is JetPack's **3.8**" | nvethernet; 3.12 |
| `tools/lan_doctor.sh` | `CAM_IF="${CAM_IF:-eth1}"`, `(expect 9000)` | `mgbe0_0`, expect **8966** |
| `pyproject.toml` | `requires-python = ">=3.8"` | 3.12 |
| `README.md`, `TRANSFER.md`, `HANDOFF.md` | "281 tests" / "179 python tests" | **362** |
| `TRANSFER.md` | `CUDA_HOME` defaults to `/usr/local/cuda-11.4` | 13.2 |
| `patgv/config.py` | `keyence.iface` default `"eth1"` — **actively harmful** | `config.yaml` overrides to `null` |

`verify_report.txt` and `verify_report_ALLGREEN.txt` are full Orin build logs. They are **historical
records, not claims** — do not "correct" them.

## Why the GVSP camera does not link

`docs/THOR-CAMERA-LINK.md` is the authoritative document. **Read it before touching anything
network-related.** The one-sentence version:

> The Lucid ATV245S-M is a fixed-rate 25GBASE-SR device, this box's QSFP28 cage is in 10G mode, neither
> side can negotiate, and no cable or optic can bridge two fixed unequal rates — the cage must be
> reflashed to 25G.

1. **The cage is not a 100G port.** It is **four independent MGBE MACs**, one per UPHY1 lane
   (lane4→`mgbe0_0` … lane7→`mgbe3_0`). NVIDIA, asked directly: *"No, the maximum is 25GbE x 4."* The
   rate is **4×10G or 4×25G, all lanes together, never mixed; default 10G**, selected by ODMDATA →
   device tree, **compiled in, not negotiated**.
2. **The camera's optic is built in.** *"25GBASE-SR LC Duplex MM Fiber Connector (OM4, 850nm)"*, and
   *"comes with a built-in optical transceiver, eliminating the need for a separate SFP module."* There
   is no SFP28 cage on the camera and no module to swap.
3. **No autonegotiation exists.** 25GBASE-SR is a fixed **25.78125 GBd** PMD, and **IEEE defines no
   autonegotiation clause for fibre PMDs** (unlike `-CR` twinax or `-KR` backplane). The camera cannot
   drop to 10G, and Thor's side is a `fixed-link` MAC with **no PHY at all**, so it cannot negotiate
   either.
4. **Result: a permanent `NO-CARRIER` — and the camera still lights its link LED, because its receiver
   sees light.** That is exactly the misleading symptom this rig presented.
5. Live device tree confirms it: `nvidia,uphy-gbe-mode = 1` (1 = 10G, 2 = 25G),
   `nvidia,macsec-enable = 1`, `fixed-link/speed = 10000`.

### Closed non-causes

Do not re-investigate these:

- **`camrtc-coe` / `tegra-capture-coe` is a red herring** — an auxiliary consumer, not the owner. Users
  run iperf3 at 10–25 Gb/s with those exact lines present. **Do not blacklist it for network reasons.**
- **No missing overlay.** All four nodes are `status="okay"` and all netdevs enumerate; the overlay
  machinery only switches 10G→25G.
- **`Port: MII, Transceiver: external, Supported link modes: Not reported` is normal** for a fixed-link
  MAC with no PHY. Users whose links are **up** post byte-identical output; only `Link detected:`
  differs.
- **MTU 1466 is explained, not a fault** — see the MACsec arithmetic below.

### Never infer link state from `speed`

`ethtool` reports `10000Mb/s` on all four lanes **while `carrier` is 0**, because that number is echoed
from the device tree. **Use `/sys/class/net/<if>/carrier`.**

This is a live bug, not a hypothetical: `native/tune_net.sh`'s `detect_iface()` selects by
`speed >= 10000`, so on a dead box it confidently picked `mgbe3_0` and tuned an interface with no cable
in it.

### The fix

1. **Reflash ODMDATA**: `uphy1-config-8,mgbe0-speed-3,mgbe1-speed-3,mgbe2-speed-3,mgbe3-speed-3`
   (`0=2.5G 1=5G 2=10G 3=25G`).
2. **Verify in the live device tree** — `uphy-gbe-mode` → 2, `fixed-link/speed` → 25000. On stock
   ODMDATA the 25G fragments are *loaded but not applied*, gated on
   `board_config { odm-data = "uphy1-config-8" }`. **"The overlay is in the flash layout" is not
   evidence.**
3. **Host optic**: NVIDIA **MAM1Q00A-QSA28** QSFP28→SFP28 adapter (it **wires QSFP lane 1 only** →
   `mgbe0_0` and nothing else) plus a Lucid **OT-SFP28-25G-GL** or Mellanox **MMA2P00-AS** (10/25G
   dual-rate, handy for bring-up), plus LC-LC **OM4** duplex.

**The on-site 100GBASE-LR4 (10Gtek ALQ28-LR4-10) is useless**, for three independent reasons: it is
4×25G WDM onto one *single-mode* pair at ~1300 nm while the camera is 850 nm *multimode*; its far end
must be another LR4 port; and its gearbox expects 25.78 Gb/s per host lane while these run 10.3125.

**Interim option**: a 25G switch in the middle with GEV `DeviceLinkThroughputLimit` below ~9 Gb/s —
ceiling **~51 fps** full-res instead of 74. That is the one topology proven twice on Thor. A plain
SFP+-to-RJ45 media converter does **not** work.

Throughput reality worth keeping in proportion: this rig needs 24.472 MB × 74 fps = **14.5 Gb/s**, which
fits at 25G but not at 10G. But **the CV chain is CPU-bound at ~2.5 Gb/s**, so **the reflash is about
making the link *exist*, not about bandwidth.**

### The MACsec 34 bytes explain three numbers

`nvethernet` **unconditionally reserves 34 bytes** per frame for MACsec (SECTAG + ICV + 2-byte
ethertype) once MACsec resources are probed. Therefore:

```
1500 − 34 = 1466      the odd default MTU these interfaces come up with
9000 − 34 = 8966      the real jumbo ceiling
8966 − 28 = 8938      the correct GVSP packet size (IP + UDP headers)
```

The `SCPS_PKT_SIZE` register's **bit30 is DoNotFragment**, which is why the packet size must be MTU−28
rather than MTU. MTU changes need the link **administratively down** or `RTNETLINK answers: Device or
resource busy`.

## `tools/thor_setup.sh`

```bash
bash tools/thor_setup.sh --diagnose     # read-only; start here
sudo bash tools/thor_setup.sh --apply   # configure
```

It exists because `sudo` needs a password on this box, so everything requiring root is collected into
one script. It **supersedes `native/tune_net.sh`**, whose bundled `ethtool` calls are rejected whole on
this driver.

Interface candidates are `mgbe0_0..mgbe3_0` and `enP2p1s0`; it **refuses**
`lo|wlP1p1s0|docker0|l4tbr0|veth.*|can[0-9]+|usb[0-9]+`, because `wlP1p1s0` is the only management path
and eleven unrelated containers own the veths. With no carrier and no `--iface` it does the sysctl and
CDI work anyway.

### What `--apply` changes

| # | Change | Why |
|---|---|---|
| 1 | `nmcli dev set <IF> managed no` | NetworkManager would re-DHCP or flush a hand-set address. The **narrow, reversible** form — this device only |
| 2 | `ip link set dev <IF> down` | **MTU must be set with the link DOWN**, or nvethernet answers "Device or resource busy" |
| 3 | `ip link set dev <IF> mtu 8966` | warns with the real `maxmtu`, "less 34 for MACsec" |
| 4 | `ip link set dev <IF> up` | |
| 5 | `ip addr add 169.254.100.1/16 dev <IF>` | idempotent |
| 6 | `ethtool -G <IF> rx <rmax>` | **RX ONLY, alone.** `-G rx 16384 tx 16384` is rejected whole because TX maxes at 4096 — **and the rejection leaves RX at 4096 too** |
| 7 | `ethtool -C <IF> rx-usecs 50` | Same trap: `-C adaptive-rx off rx-usecs 50` fails as a unit, leaving rx-usecs at its 512 default. **Alone it sticks** |
| 8 | `echo 1 > /sys/class/net/<IF>/threaded` | **Threaded NAPI — "the single highest-leverage runtime knob on these MACs."** Not sticky across reboot, which is why it lives here |
| 9 | `echo DMA-FQ > /sys/kernel/iommu_groups/<grp>/type` | deferred DMA unmap, per NVIDIA's 25GbE page |

Items 6 and 7 are the same class of trap and worth internalising: **`ethtool` rejects a multi-key
invocation as a unit**, and the rejection silently leaves *every* key at its old value. Set one key per
call on this driver.

### Kernel receive path

Persisted to `/etc/sysctl.d/60-patgv-camera.conf`:

| sysctl | Value |
|---|---|
| `net.core.rmem_max` | **536870912** (512 MiB) |
| `net.core.rmem_default` | 33554432 (32 MiB) |
| `net.core.wmem_max` | 536870912 |
| `net.core.optmem_max` | 33554432 |
| `net.core.netdev_max_backlog` | **250000** |
| `net.core.netdev_budget` | 60000 |
| `net.ipv4.conf.all.rp_filter` | **2** (loose) |
| `net.ipv4.conf.<IF>.rp_filter` | **2** (loose) |

`rp_filter` must be loose because "the camera subnet is link-local and asymmetric. Strict reverse-path
filtering silently drops those packets; loose keeps the spoofing protection."

**The sizing argument, quoted:**

> One 24.5 MB frame at MTU 8966 is ~2800 packets. The stock 208 KiB socket buffer against a 24.5 MB
> burst is not a marginal shortfall, and any "lossless" claim made without these values is meaningless.

Untuned, `rmem_max = 212992` is **under 1% of one frame** and `netdev_max_backlog = 1000` — **~600× too
small**. `--diagnose` flags `rmem_max < 134217728` and `netdev_max_backlog < 8192` as `<-- TOO SMALL`.

### It must be re-run every boot

**Only the sysctls persist.** Not sticky: threaded NAPI, the RX ring size, `rx-usecs`, IOMMU DMA-FQ,
`nvpmodel -m 0`, `jetson_clocks`, the nmcli-unmanaged mark, and the static IP.

**There is no systemd unit for it in this tree.** `native/install-camera-net.sh` wired the *Orin* tuner
into `gv-camera-net.service`; there is no Thor equivalent yet. If the rig comes up after a reboot with
frames dropping, this is the first thing to check.

Next step after `--apply`: prove ordinary UDP before blaming GVSP —
`ping -M do -s 8938 -c 3 <camera-ip>`, then `cd native && python3 gv_discover.py --iface <IF>`.

## Docker and the GPU

```bash
docker build -t patgv:thor .
docker run --rm --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all --network host \
  -v "$PWD/config.yaml:/app/config.yaml:ro" -v "$PWD/data:/app/data" patgv:thor
```

Two stages: nvcc 13.2, then python 3.12.

**GPU in Docker works, and needs `--runtime=nvidia` *plus* `NVIDIA_VISIBLE_DEVICES`. Neither alone is
enough**, and `--gpus all` is **refused outright** because the toolkit auto-detects CSV mode on Tegra.

> **NEVER use `--gpus all` on this host.**

The earlier conclusion that "GPU-in-Docker does not work" came from omitting `NVIDIA_VISIBLE_DEVICES`,
without which the hook injects nothing at all. Verified 2026-08-31 with `gv_measure` in a plain
`ubuntu:24.04` container producing results identical to the host.

`libcuda` is injected to **`/opt/nvidia/l4t-gpu-libs/openrm`**, not `/usr/lib/aarch64-linux-gnu`. So:

```bash
ldconfig -p | grep libcuda        # the check that means something
ls /usr/lib/.../libcuda*          # the one that misleads
```

**The docker compose plugin is absent** on this host — only buildx and trust are in
`/usr/libexec/docker/cli-plugins`.

### CDI is optional

CDI is **entirely optional here, and the script says so "because the sibling project recorded the
opposite."** GPU-in-Docker already works via the CSV-mode hook. If you do generate it:

```bash
nvidia-ctk cdi generate --mode=csv --output=/etc/cdi/nvidia.yaml
```

**`--mode=csv` is required.** Default `--mode=auto` detects `nvml` here and dies with *"failed to
initialize NVML: Driver Not Loaded"*, because JetPack 7's driver layout has no version-suffixed libcuda
for `nvcdi`. **That is also why `nvidia-cdi-refresh.service` sits in `failed` state on this host** — it
is expected, not a fault to chase.

## GenICam registers: write the raw integer

Exposure, gain and frame rate are GenICam **converters over integer raw registers, not floats.**
Writing a float's bits gets clamped to garbage.

```
ExposureTimeRaw = microseconds × 125     (raw unit = 8 ns; 1 µs / 8 ns = 125)   0x10310110
GainRaw         = dB × 10                                                       0x10900104
AcquisitionFrameTime = integer microseconds;  fps = 1e6 / frametime_us          0x10300014
Auto enums: Off=0  Once=1  Continuous=2                        0x10310124 / 0x10900118
```

Readback divides by the same constants, so the round-trip is where the convention is observable.

From Python you never touch a register: `gvctl` takes `exp <us>|auto`, `gain <db>|auto`, `detect toggle`,
and the µs↔raw conversion happens inside `gv_pipeline`.

Note a contradiction in the header: `REG_ACQ_FRAMERATE = 0x10300014 // float register (Hz)` and
`REG_ACQ_FRAMETIME = 0x10300014 // integer microseconds` are the **same address with two contradictory
descriptions**. `native/README.md` sides with the integer-µs reading.

Two operational traps:

- **The camera clamps exposure to the frame period.** With no `--fps` cap, a few brightness steps hit
  that ceiling and stick. Recover with exposure → auto.
- **`DeviceLinkThroughputLimit` has a pathological ~12 Gb/s regime** on this camera — prefer free-run,
  which is why `limit_bytes: 0` ships.
- **Binning changes µm/pixel** (2×2 doubles it, so recalibrate). **Cropping the ROI does not.**

## `verify_on_jetson.sh` — 13 gates, in order

```bash
bash verify_on_jetson.sh            # everything; writes verify_report.txt
bash verify_on_jetson.sh --quick    # skip gpu-all-parity, the slow gate
bash verify_on_jetson.sh --no-build
```

**Exit code = number of failed steps.** Deliberately **not** `set -e`: "A failing step must not stop the
run: the most useful outcome is a complete picture of what works and what does not, and an early exit
would hide the later results behind the first problem." Runtime ~5–15 min.

| # | Gate | Note |
|---|---|---|
| 0a | complete-tree preflight | **Runs before the report is even opened**, so the message cannot get buried. Exits **90**. An incomplete tree produces a dozen unrelated-looking failures that read like a broken port. Warns **not** to delete the tree first — `data/labels.db` and `data/runs.db` are deliberately not in the archive |
| 0b | environment probe | Imports `numpy cv2 yaml aiohttp watchdog torch paho.mqtt scipy skimage pytest pytest_asyncio` + `torch.cuda.is_available()`. **This is the block that catches the silent-skip trap** — check `pytest_asyncio` and `paho.mqtt` read OK, not MISS |
| 1 | `make distclean` | **First, always** — see [native-chain.md](native-chain.md) |
| 2 | `make -j$(nproc)` | |
| 3 | `make frontend_check objects_check` | `all` builds neither, and no parity target depends on them |
| 4 | **`c2-parity`** | CPU chain vs the frozen oracle |
| 5 | **`live-parity`** | `ObjectStage` — the path every live frame takes |
| 6 | `gpu-all-parity` | skipped by `--quick` |
| 7 | `frontend_check` | C1 vs oracle. **`set -o pipefail` is load-bearing** here: without it `./prog \| tail` exits 0 even when prog does not exist, so a missing binary reports as a PASS. "A verification script that can report false green is worse than no verification script." |
| 8 | `objects_check` | live labels path == CPU-CCL path |
| 9 | `gv-measure-smoke` | the file front door opens |
| 10 | `gv_pipeline --selftest` | offline GVSP reassembly |
| 11 | `gv_pipeline --cuda-check` | mapped zero-copy pool |
| 12 | `--objdump` presence | on NO: "this binary predates the flag; the GVSP population would fall back to the overlay file and be biased against small particles" |
| 13 | python tests | `pytest tests/ -q` |
| 14 | **end-to-end join** | `tools/verify_end_to_end.py` — "The gates prove each half. This proves they fit together" |

Nothing here needs a camera, an FTP upload or a broker. On failure: *"send that file back rather than a
screenshot; the failing command's own output is what identifies the cause."*

## `docs/` inventory

| File | Solves |
|---|---|
| `THOR-CAMERA-LINK.md` | Why the GVSP camera does not link and exactly what fixes it. **The authoritative physical-layer document** |
| `CALIBRATION.md` | Deriving `um_per_pixel` per camera, and why both shipped `1.0` values corrupt every D-value |
| `CV-TUNING.md` | Trustworthy CV on all three paths via `tools/cv_doctor.py`; what each rejection reason means |
| `FTP-SETUP.md` | Standing up the second camera's drop folder, and proving each link in order |
| `LAN-HOSTING.md` | Serving the dashboard from boot, and why `169.254.100.1` must never reach an operator |
| `RUNNING-EXPERIMENTS.md` | The whole run loop: start, record, where every byte lands, how to judge the measurement |
| `WATCHDOG.md` | The transport-independent directory path, the player, sessions, partial uploads |
