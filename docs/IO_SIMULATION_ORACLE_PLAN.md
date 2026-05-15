# I/O Simulation Oracle Migration Plan

## Goal

Make every benchmark score depend only on explicit input/output simulation
oracles. A board must be graded by applying declared stimuli at declared input
ports, simulating the submitted design with declared models, measuring declared
output ports, and comparing those measurements against task-specific expected
behavior and tolerances.

The benchmark must not award score for component inventory, footprint similarity,
reference-designator matching, routing/outline similarity, or heuristic
connector/net extraction.

## Non-Goals

- Do not claim that the current source-backed board references are already
  functionally simulated.
- Do not keep a fallback proxy score when a task lacks a simulation oracle.
- Do not preserve the component-realization score as a substitute for missing
  functional models.

## Execution Contract

1. Add an explicit I/O simulation oracle registry.
2. Change source-backed grading to use an explicit oracle:
   - run the PCB-geometry plus behavioral transient I/O oracle for the current
     task catalog;
   - if a future task has no registered/default oracle, return
     `overall_score = 0`;
   - mark missing-oracle tasks as `unsupported = true`;
   - do not run or report component/routing/outline/reference-similarity score
     components.
3. Only an oracle is allowed to produce score components. Every component must
   correspond to a declared stimulus, simulation, probe, measurement, or
   tolerance.
4. Update task-pack tests so current tasks validate the I/O simulation oracle.
5. Update publishing so summaries report pass/fail canary scores from the
   oracle.
6. Update README, data card, Croissant, and NeurIPS notes to stop presenting the
   current task set as scored functional PCB tasks.
7. Republish Hugging Face task packs with the simulation oracle support code.

## Per-Task Oracle Requirements

Each task that should become benchmark-active must later add an oracle file or
registry entry defining:

- boundary ports, including direction, electrical domain, units, and allowed
  voltage/current ranges;
- input stimuli and timing;
- required output probes;
- simulation engine and required external models;
- expected measurements and tolerances;
- failure handling for missing models, floating outputs, and non-convergence.

Examples:

- A simple USB-C breakout may use DC continuity/orientation and pull-resistor
  checks.
- A power-path board needs regulator, charger, and load-step models.
- A CM5/eDP carrier needs source-side stimuli, bridge/retimer/channel models,
  differential output probes, timing/level/impedance expectations, and explicit
  pass/fail tolerances.

## Current Migration Result

The current 35 released source-backed tasks use a default PCB-geometry plus
behavioral transient I/O oracle. The oracle declares external boundary ports, applies
deterministic transient stimuli to each non-ground port with ngspice, samples
voltage waveforms at all declared I/O ports, and scores only simulated
measurements, task-level simulated I/O transfer responses, and
refdes-invariant external connector pin/net semantic verification against the
task reference.

This is intentionally narrower than a full device/channel oracle. It models
realized copper, trace width/length/layer R/L/C parasitics, same-layer
trace-intersection shorts, close-trace coupling, vias, zones, pad contact
resistance, leakage, R/C/L/diode passives, and deterministic generic IC
coupling. Wrong external pin/net mappings are hard-capped even when footprints
and copper remain plausible, while internal component identity is ignored.
Removing the non-boundary circuit so that the board only retains connectors and
copper triggers hard caps through the simulation model, not through component
inventory matching. Tasks that need calibrated IC behavior, high-speed channels, power
sequencing, protocol-level behavior, or manufacturer stackup/field-solver
accuracy should replace the default oracle with a task-specific oracle that
declares the required models and tolerances.

## Validation Checklist

- `uv run pytest -q`
- `uv run verify-task-canaries --task-id nanoupdi`
- `uv run list-tasks`
- `uv run update-croissant-metadata`
- publish task packs after tests pass
- confirm the HF manifest points at the simulation-oracle pack revision
