# EDA Bench Data Card

## Purpose

EDA Bench uses explicit I/O simulation oracles for KiCad PCB tasks. Current
public source-backed tasks are scored with an ngspice PCB-geometry plus
behavioral transient I/O oracle: declared external ports receive deterministic
transient stimuli, refdes-invariant external I/O semantic and topology
contracts are checked without reference designator matching, actual routed
copper is modeled as trace width/length/layer
parasitics with same-layer trace-intersection shorts and close-trace coupling,
voltage waveforms are sampled at declared I/O ports, and the simulated
measurements plus task-level I/O transfer responses and PCB geometry profiles
are compared to the task reference.

## Agent-Visible Inputs

During benchmark execution, evaluated agents receive only:

- the task prompt and task metadata mounted at `/task`
- a writable `/workspace/final_project`
- the pinned agent Docker image with KiCad, ngspice, Python, Node, and Codex
- web access through the built-in Codex harness

Reference projects, source snapshots, canaries, grader code,
`functional_contract.json` task-semantic verifier contracts, and
`io_contract.json` static verifier contracts are public in the Hugging Face full
task packs, but are not mounted into the evaluated agent runtime.

## Reference Artifacts

Each task is anchored to a vendored snapshot of an upstream open hardware design.
The Hugging Face full task pack records the upstream URL, commit or release
identifier, license note, source snapshot, and reference project used by the
grader. It also includes `functional_contract.json`, the task-semantic
external-interface contract, and `io_contract.json`, the static
refdes-invariant external-I/O semantic, topology, and PCB-geometry contract used
by the grader.
These references and contracts are not mounted into the evaluated agent runtime,
but they are public benchmark artifacts and the upstream designs may also be
discoverable by web-enabled agents.

These references are retained for provenance and I/O oracle targets. They are
not used to award proxy score for project validity, component inventory,
footprint similarity, routing similarity, outline similarity, or physical
plausibility.

## Contamination Policy

The default benchmark should be reported as web-enabled hardware task solving
under a fixed public-source access policy. Agents may use web search and may
discover public upstream projects, just as public software-engineering
benchmarks may expose code history, issue threads, or patches. Claims should
therefore be limited to public-source EDA task solving under fixed prompts,
fixed tooling, access policy, and recorded provenance. Do not use default
leaderboard results as evidence of closed-book synthesis or
memorization-resistant hidden answers.

Repository build artifacts should contain runner and harness code, public
documentation, the task-pack manifest, and loader/grader support code. Task
instances, reference PCB projects, upstream snapshots, canary answer
submissions, task metadata, and Croissant metadata are hosted in Hugging Face
task packs. Python wheels and source distributions are tested to exclude
`tasks/*/gold/**`, `third_party/upstream_designs/**`, `source_snapshot/**`, and
canary answer submissions.

For hidden-evaluation claims, create a separate sealed split with
non-public or newly authored boards, non-identifying prompts, private grader
access, and a web-disabled or tightly specified web policy.

## Task Coverage

The public task catalog has 35 released source-backed KiCad task artifacts. They are
score-supported through explicit I/O simulation oracles:

- 2 very easy, 5 easy, 4 medium, 12 hard, 7 very hard, and 5 extreme tasks.
- Compact external-I/O tasks cover USB-C breakouts, GPIO expanders, logic-level
  conversion, UART, RS-485, and simple connector adapters.
- Mid-size boards cover USB/debug tools, battery charging and power-path boards,
  RP2040/RP2350 development boards, camera/display adapters, audio, LoRa, and
  mixed-signal, keyboard-matrix, and motor-driver interfaces.
- Large boards cover CM4/CM5 carriers, Jetson Orin carriers, PCIe/M.2 adapters,
  Zynq SoMs, and dense multi-rail baseboards.

## Grader Validation

Full task packs include tests for the explicit I/O oracle. The reference project
must score `1.0` through `score_components["io_simulation"]`, and the fail
canary must score below the release threshold using the same simulation oracle.
Fail canaries remove active internal circuitry when available, falling back to
external boundary removal for passive boards, so validation covers plausible
external shells that do not contain the circuit needed to work.

The task-pack builder also stages generated mutation canaries for missing board
outlines, unrouted external nets, isolated external pads, external power/signal
pads tied to ground, and missing high-speed-like routes for high-speed carrier
tasks. Four representative calibrated tasks currently add stricter task-family
checks: USB-C breakout, RS-485 transceiver breakout, BQ24295 power path, and
M.2/PCIe adapter.

A full generated-mutation sweep on May 6, 2026 validated the original 40-task
candidate set and 162 generated mutation canaries below the release threshold;
the 35 released tasks are the license-triaged subset of that validated set.

Experimental swapped-connector-pin and active-device-without-power mutations are
implemented but are not part of the validated release-canary set. Task-family
passive mutations such as missing pull-ups, required configuration passives, and
missing decoupling should be added only where the corresponding task contract
identifies those passives as required behavior.

## Evaluation Claims

Current public task scores support only claims tied to the declared PCB-geometry
plus behavioral transient I/O simulation oracle. Scores should not be interpreted as
direct proof of electrical safety, regulatory compliance, manufacturability,
production readiness, or high-speed protocol compliance.

| Claim | Status |
|---|---|
| Open-book agent task solving under fixed prompts/tools/provenance | Supported |
| External I/O behavior under the released oracle | Supported |
| Closed-book PCB synthesis | Not supported |
| Manufacturing, regulatory, thermal, EMC, or production readiness | Not supported |
| Exact component inventory, reference designator, outline, or route-shape matching | Not a primary score |

## Known Limitations

- The current oracle models realized copper, trace width/length/layer R/L/C
  parasitics, same-layer trace-intersection shorts, close-trace coupling,
  vias, zones, pad resistance, leakage, R/C/L/diode passives, deterministic
  generic IC coupling, task-required boundary-net interface families,
  task-required generic internal active-role realization,
  broad component-function realization for active devices, passives,
  decoupling, filters, and protection networks,
  active-device power/ground integrity,
  absolute fabrication geometry sanity for outlines, trace widths, and via
  annular rings,
  external-net and board-wide same-layer short electrical-health contracts,
  refdes-invariant external
  connector pin/net semantic contracts, generic signal net-name tolerance,
  KiCad DRC and schematic ERC errors relative to the reference when
  `kicad-cli` is available,
  diagnostic exact reference-pad, role/topology, and route-shape checks, hard
  caps for wrong external pin/net mapping, missing routed copper, split or isolated external I/O,
  power/ground/signal shorts, missing simulated signal or I/O transfer
  responses, missing task-required internal active realization, missing
  component-function realization, missing active-device power integrity,
  DRC/ERC error violations, implausible trace/via/outline fabrication geometry,
  grossly implausible impedance, and missing or implausible differential-pair
  families. Many public hardware
  tasks still need richer calibrated models: device behavioral models,
  IBIS/SPICE/S-parameter data, field-solver stackups, power sequencing,
  differential-channel expectations, and task-specific tolerances.
- The benchmark disables proxy grading based on component, footprint, routing,
  or outline similarity.
- The built-in web harnesses are web-enabled. Agents may be able to discover public
  upstream projects through search, so results measure web-enabled agent
  performance under the disclosed access policy rather than closed-book design
  synthesis.
- Some upstream projects have restrictive or unclear redistribution terms. See
  `LICENSES.md`, `docs/RELEASE_LICENSE_TRIAGE.md`, and per-source license
  notices before republishing subsets. The current conservative risk inventory
  is `cm5io_official`, `mixed_signal_stm32_dev_board`, `rp2350b_dev_board`,
  `stm32f_audio_codec`, and `ef28_badge`. These should be released in public
  full packs only with explicit permission, an acquisition-script replacement,
  or quarantine from redistributed references and source snapshots.
- The current canary suite validates frozen references, structural fail canaries,
  and generated mutation canaries. Additional mutation types should be added for
  future releases, especially task-family passive removals for missing pull-ups
  and missing decoupling.

## Maintenance

Task prompts, references, source metadata, canaries, and task-pack revisions are
hosted in the Hugging Face dataset recorded in `tasks/task_pack_manifest.json`.
Machine-readable Croissant 1.0 plus Croissant RAI metadata is generated from the
HF task catalog and manifest.
