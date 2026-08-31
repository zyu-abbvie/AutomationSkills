# Mix setpoint maths, units and ceilings

Everything in this file is taken from `$PROD/LNP_418/ignition/script-python/LNP/code.py`, which is the
only implementation in the family with the arithmetic in one place. The other instances compute the
same quantities inside `views/main/view.json` event handlers.

## The six operator inputs

Read by `read_inputs(component)` from sibling numeric-entry fields. **The caller must be their
sibling** — the function walks `component.getSibling(name)`, so calling it from elsewhere in the tree
logs a warning and silently returns the fallback.

| Input | Component name | Unit | Default | Meaning |
|---|---|---|---|---|
| `mRNA_flow` | `mRNA_flow_SP` | mL/min | `0` | The mRNA (aqueous) leg. Every other flow derives from this. |
| `mRNA_vol` | `mRNA_vol_SP` | mL | `0` | Volume to dispense on the mRNA leg. |
| `ratio` | `Ratio_PU1_PU2` | — | `3` | mRNA : lipid flow ratio. Lipid leg is `mRNA_flow / ratio`. |
| `ratio_d1` | `Ratio_D1` | — | `1` | First quench dilution divisor. |
| `ratio_d2` | `Ratio_D2` | — | `0.5` | Second quench dilution divisor. |
| `compensate` | `compensate` | **seconds** | `0` | Start stagger between PU1 and PU2. Not a flow. |

`compensate` sitting in the same block as five flow/ratio numbers is the single most misread parameter
in the family. It is a time.

## Derivation

```python
lipid_flow   = mRNA_flow / ratio
mixer_outlet = mRNA_flow + lipid_flow

flows = {
    'PU1': mRNA_flow,
    'PU2': lipid_flow,
    'PU3': mixer_outlet / ratio_d1,
    'PU4': mixer_outlet * (1.0 + 1.0 / ratio_d1) / ratio_d2,
}
volumes = {
    'PU1': mRNA_vol,
    'PU2': mRNA_vol / ratio,
}
```

The physical reading: `PU1` and `PU2` are the two legs that meet in the mixer. `PU3` and `PU4` are the
quench, and `start_quench()` starts exactly those two.

**`PU4` does not scale off `PU3`.** It scales off `mixer_outlet × (1 + 1/ratio_d1)` — the combined
mixer outlet *plus* the first quench addition, i.e. the total stream arriving at the second stage.
Reimplementing this as `PU3 / ratio_d2` is wrong and is the most common arithmetic error here.

### Worked example

`mRNA_flow = 10`, `ratio = 3`, `ratio_d1 = 1`, `ratio_d2 = 0.5`, `mRNA_vol = 60`:

```
lipid_flow   = 10 / 3            = 3.333   mL/min   -> PU2
mixer_outlet = 10 + 3.333        = 13.333  mL/min
PU3          = 13.333 / 1        = 13.333  mL/min
PU4          = 13.333 x (1+1/1) / 0.5
             = 13.333 x 2 / 0.5  = 53.333  mL/min
PU1 volume   = 60                = 60.000  mL
PU2 volume   = 60 / 3            = 20.000  mL
```

Every published number is rounded to 3 decimals, so `3.333`, `13.333`, `53.333`.

With `ratio_d1 = 2` instead, `PU3` halves to `6.667` but `PU4` becomes
`13.333 × 1.5 / 0.5 = 40.000` — it drops, but not proportionally. The `(1 + 1/ratio_d1)` term is why.

## Guards, in the order they fire

```python
if ratio <= 0 or ratio_d1 <= 0 or ratio_d2 <= 0:
    raise ValueError('ratios PU1:PU2, D1 and D2 must all be greater than zero')
if mRNA_flow < 0 or mRNA_vol < 0:
    raise ValueError('mRNA flow and volume setpoints cannot be negative')
```

All three ratios are divisors, so zero or negative is rejected before any arithmetic. The `ValueError`
message is written to be shown to the operator verbatim — `apply_setpoints` catches it and routes it
through `notify()`.

Then, after computing but **before publishing anything**:

```python
over = []
for pu in PUMPS:
    if flows[pu] > max_flow[pu]:
        over.append('%s %.3f exceeds %g' % (pu, flows[pu], max_flow[pu]))
if over:
    raise ValueError('flow limit (mL/min): ' + ', '.join(over))
```

**Setpoints apply as a set or not at all.** One pump over its ceiling aborts the whole apply, and
nothing is published. A silent no-op at the panel with unchanged device values means this fired —
check `view.custom.Status`, which `notify()` writes as a layout-independent message bus.

## Flow ceilings

| Pump | Ceiling | Source |
|---|---|---|
| `PU1` | 200.0 mL/min | `MAX_FLOW` constant — fixed by loop hydraulics |
| `PU2` | 200.0 mL/min | `MAX_FLOW` constant |
| `PU3` | 200.0 mL/min | `MAX_FLOW` constant |
| `PU4` | **runtime** | `[MQTT Engine]…/PU4/HMI_COM/FeedMaxFlowRate`, fallback `3400.0` |

`PU4` is a MasterFlex whose ceiling depends on installed tubing, so the UI publishes the tubing size
as `FeedMaxFlowRate` and the script reads the tag rather than the dropdown — deliberately, so it works
from any component without a cross-container reference. If the read fails or quality is bad it logs
and falls back to `3400.0`.

**The fallback is roughly 17× the fixed pumps' ceiling.** If the tubing tag is unavailable, an
otherwise-invalid `PU4` setpoint can pass validation. Confirm `FeedMaxFlowRate` is live before trusting
a `PU4` limit check.

`LNP_opt` uses a different and incompatible table, in `shared/PumpControl`:

| Pump | Type | Min | Max |
|---|---|---|---|
| `PU1` | Syringe | 0.001 | 50.0 mL/min |
| `PU2` | Syringe | 0.001 | 50.0 mL/min |
| `PC01` | Peristaltic | 0.1 | 600.0 mL/min |
| `PU04` | Mixed | 0.1 | 500.0 mL/min |

Note it enforces a **minimum** as well as a maximum, and validates on `abs(flowRate)` so a reverse
(negative) setpoint is checked on magnitude. `LNP_418` has no minimum.

## Rounding

```python
DECIMALS = 3
def _round(value):
    return round(float(value), DECIMALS)
```

One rule for every published setpoint. The module header records why:

> before it existed the master panel published `round(value, 3)` while the PU2 field published
> `round(value, 2)` and the PU3 field published `int(round(value))`, so the same setpoint reached the
> device as 58.667, 58.67 or 59 depending on which control the operator touched last.

The ratios themselves are published at **6** decimals (`round(inputs['ratio'], 6)`), not 3, because
they are recipe context rather than a device setpoint. `compensate` is published at 3.

If you add a control that publishes a setpoint, route it through `set_flow` / `set_volume` /
`apply_setpoints`. A direct `publish()` from a view handler reintroduces exactly this defect.

## Retained recipe context

After a successful apply, four values are published retained so the historian and any recall UI can
read back the ratios a run was executed with:

```
/PU1/Ratio      /PU1/Ratio_D1      /PU1/Ratio_D2      /PU1/Compensate
```

All four hang off **`PU1`** regardless of which pump they affect — `Ratio_D2` governs `PU4` but lives
under `PU1`. Do not infer pump ownership from the topic prefix here.

Some instances expose `PU1/Ratio_D` (no digit) in their views alongside `Ratio_D1`/`Ratio_D2`. Probe
before binding; see `command-contract.md` on topic-name drift.

## Reset

`reset()` stops all four pumps, publishes `0` to every flow and volume setpoint topic, and clears the
three panel inputs `mRNA_flow_SP`, `mRNA_vol_SP`, `compensate`. It does **not** clear the three ratio
fields, and it does not republish the retained `Ratio*` context — so after a reset the retained recipe
values still describe the previous run.
