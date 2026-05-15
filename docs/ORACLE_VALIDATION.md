# Oracle Validation Notes

These notes collect the reviewer-facing validation story for the current public
source-backed task set.

## What The Oracle Scores

Every active task is scored through `score_components["io_simulation"]`.
Unsupported future tasks fail closed with score 0. The oracle records:

- declared external ports, stimuli, probes, simulator, models, expected
  measurements, and tolerances;
- refdes-invariant external connector pin/net semantics;
- routed external-net coverage, split nets, isolated pads, and external short
  safety;
- PCB-derived trace parasitics, same-layer intersection shorts, close-trace
  coupling, vias, zones, pad resistance, and leakage;
- deterministic generic R/C/L/diode/passive and generic IC coupling models;
- broad active-device, component-function, active-power, DRC/ERC, fabrication,
  and high-speed differential-pair caps.

Four representative tasks also use calibrated task-family checks layered on top
of the default oracle:

| Task | Calibration |
|---|---|
| `usb_c_female_breakout` | USB-C breakout continuity and connector-orientation checks |
| `rs485_transceiver_breakout` | RS-485 active-transceiver connector, component-function, and active-power checks |
| `bq24295_power_path_board` | Charger/power-path component-function, active-power, and external-power safety checks |
| `m2_pcie_adapter` | M.2/PCIe connector semantics and high-speed differential-pair geometry checks |

## Release Controls

| Control | Result |
|---|---|
| Pass canaries | 35/35 released frozen reference projects score 1.0 |
| Fail canaries | 35/35 released structural fail canaries score at most 0.15 |
| Generated mutation canaries | 162 generated mutations across the original 40-task candidate set pass below the 0.75 threshold |
| Fail threshold | 0.75 |
| Missing oracle behavior | unsupported task returns 0.0 |
| Public package boundary | tests enforce exclusion of `tasks/*/gold/**`, upstream snapshots, and canary submissions from wheels/sdists |
| Calibrated-task sweep | USB-C, RS-485, BQ24295, and M.2/PCIe references score 1.0 and their generated mutation canaries score below 0.75 |

## Mutation Canaries

The task-pack builder now stages generated mutation canaries under
`canaries/mutations`. The current generated mutations are:

- missing board outline;
- unrouted external nets;
- isolated external pads;
- external power/signal pads tied to ground;
- missing high-speed-like routes for high-speed carrier tasks.

Two additional generic mutation families are implemented experimentally, but are
not part of the validated release-canary set:

- swapped external connector pins;
- signal-bearing active devices with power/ground pads disconnected.

The current fail canary still removes active internal circuitry when possible
and falls back to external boundary removal for passive boards. This validates
that plausible external shells are rejected. The generated mutation canaries add
coverage for common concrete failure modes, but are not exhaustive.

Future mutation additions should include task-family passive removals such as
missing pull-ups, required configuration passives, and missing decoupling. These
should be added only where the task contract identifies the passive role as
required behavior. The May 6, 2026 full sweep took 2012 seconds with three local
workers; the slowest task was `jetson_orin_baseboard` at 1252 seconds.

Those failure modes are already represented by score caps in the oracle and by
baseline failures in `docs/FAILURE_TAXONOMY_20260506.md`.
