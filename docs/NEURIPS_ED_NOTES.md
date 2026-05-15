# NeurIPS E&D Framing Notes

Use this language when drafting the benchmark paper or artifact appendix.

## Benchmark Claim

EDA Bench is a web-enabled benchmark for hardware task-solving agents under a
fixed public-source access policy. Evaluated agents receive only mounted runtime
task packs. Released full task packs with references, upstream snapshots,
canaries, and grader tests are public artifacts hosted on Hugging Face, and the
underlying upstream hardware projects may also be discoverable through web
search. The benchmark therefore measures public-information use, EDA tool
operation, and validation under fixed prompts, fixed tooling, recorded
provenance, and a disclosed access policy.

Do not frame default results as closed-book PCB synthesis, memorization-resistant
hidden-answer evaluation, or proof that the model independently invented the
design.

For NeurIPS E&D, foreground the evaluation claim: EDA Bench defines what it
means for a web-enabled agent harness to reconstruct a PCB under a declared
external-I/O oracle, and it reports the assumptions and limits of that claim.
The paper should explicitly say what is supported, what is not supported, and
what artifact controls calibrate the score.

## Artifact Split

Repository artifacts:

- runner and harness code
- task-pack loader/grader support code
- public documentation and license notes
- package builds that exclude concrete task instances and source snapshots

Hugging Face task artifacts:

- runtime prompts and task metadata
- reference PCB projects not mounted into the evaluated agent runtime
- vendored upstream design snapshots
- canary answer submissions
- full grader validation packs
- Croissant metadata and task-pack data card

## Contamination Policy

Public upstream designs may be discovered by web-enabled agents. This is a
reproducibility and realism tradeoff, similar to public software-engineering
benchmarks where code history and patches may be visible. Papers and
leaderboards should identify the task-pack revision, agent web-access policy,
model/tool versions, and the public task artifact revision. Default released
task artifacts are public, so the benchmark should not be used for closed-book
claims.

For a hidden-evaluation claim, create a sealed split with non-public or
newly authored boards, non-identifying prompts, a private grader, and either
web-disabled agents or a tightly specified web policy.

## Score Interpretation

The current public source-backed task set is scored by an explicit ngspice I/O
oracle. The oracle declares external boundary ports, applies deterministic
transient stimuli to each non-ground port, samples voltage waveforms at all
declared I/O ports, simulates routed trace width/length/layer parasitics,
same-layer trace-intersection shorts, and close-trace coupling, and compares
those simulated measurements and task-level I/O transfer responses to the
task reference.

The current oracle models realized copper, vias, zones, pad resistance, leakage,
trace parasitics, R/C/L/diode passives, and deterministic generic IC coupling.
It also verifies refdes-invariant external connector pin/net semantics, so a
wrong external pin mapping is capped even when the board still contains
plausible footprints and copper. For active tasks, it checks generic internal
active-role realization without exact component identity, and it compares broad
component-function profiles for active devices, passives, decoupling, filters,
and protection networks. It also requires signal-bearing active devices to have
power and ground connectivity when the reference does, and detects same-layer
shorts across the full routed board rather than only at external interfaces.
It applies absolute board-outline sanity checks and reference-relative trace
width and via annular-ring sanity checks so upstream design quirks do not make
the frozen pass canary fail.
When `kicad-cli` is available, it also runs KiCad PCB
DRC with schematic parity and schematic ERC, then caps excess submission errors
relative to the reference. It is not a manufacturer-calibrated behavioral model
for ICs, exact stackups, high-speed channels, power sequencing, or protocol-level
behavior.
Component inventory, footprint similarity, reference-designator matching,
routing/outline similarity, and heuristic connector/net extraction are not
scoring signals. Boards that leave only boundary footprints and routed copper
without the required simulated signal or I/O transfer responses are capped as
non-functioning submissions, even when their connector and copper geometry still
parse.

## Validation Evidence To Report

Report oracle validation by task:

- supported tasks declare their simulator, models, stimuli, probes, expected
  measurements, and tolerances
- unsupported tasks, if added later without an oracle, return zero score with
  the missing-oracle reason
- pass/fail canaries are interpreted only through the explicit oracle
- fail canaries remove active internal circuitry when available, falling back to
  external boundary removal for passive boards
- proxy/component/routing/outline diagnostics are not aggregate scoring signals

The release process should run `verify-task-canaries --run-pack-pytest` for the
HF-hosted full task packs and keep the resulting summaries with the artifact.

## Targeted Improvements Before Submission

Highest leverage for moving from borderline accept to accept:

- Add a compact oracle-validity section with task-family examples, pass/fail
  canary results, and score controls. See `docs/ORACLE_VALIDATION.md`.
- Add a failure taxonomy from saved grading artifacts. See
  `docs/FAILURE_TAXONOMY_20260506.md`.
- Add a related-work comparison table that includes PCB-Bench, OmniSch,
  HWE-Bench, PCBSchemaGen, SchGen, CircuitLM, and CAD benchmarks.
- Calibrated task-family checks now exist for USB-C breakout, RS-485, BQ24295
  power path, and M.2/PCIe. Do not oversell these as vendor-accurate models;
  they are stricter bindings on already measured oracle signals.
- Generated mutation canaries stage missing-outline, unrouted-I/O, isolated-pad,
  ground-tie, and high-speed-route-removal mutations. A May 6, 2026 sweep
  validated 162 generated mutation canaries across the original 40-task
  candidate set. Experimental swapped-connector-pin and active-device-without-power
  mutators exist, but they are not part of the validated release-canary set.
- Add access-policy baselines before final submission when they finish in time:
  no-web, retrieval/copy upper bound, oracle-aware repair, and a small
  human/expert sample. Six completed full no-web sweeps are available in
  Hugging Face provenance and should be reported as calibration controls. See
  `docs/ACCESS_POLICY_BASELINES.md` and `docs/NO_WEB_RUNS_20260506.md`.
- Run license triage before publishing a NeurIPS task-pack revision. Sources
  marked unlicensed or upstream-terms-only need explicit permission, acquisition
  scripts, or quarantine from the public full pack. The current conservative
  risk inventory is five tasks, giving a 35-task redistribution-safe full-pack
  public release. See `docs/RELEASE_LICENSE_TRIAGE.md`.
