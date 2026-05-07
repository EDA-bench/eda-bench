# EDA Bench Licensing And Redistribution Notes

The benchmark harness code is separate from the upstream hardware design
snapshots used as grading references. This code release does not vendor upstream
PCB projects, canary submissions, source snapshots, or full task-pack archives.

Runtime and full task packs are hosted in the Hugging Face dataset recorded in
`tasks/task_pack_manifest.json`. Each full source-backed task pack records the
upstream source URL, commit or release identifier, license label, and local
license or attribution notes for the corresponding hardware design.

Published runtime task packs intentionally exclude reference projects, upstream
source snapshots, canaries, and grader support code. They contain only the task
prompt, task metadata, and a README. This keeps answer artifacts out of the
mounted agent runtime.

Public Python wheels and source distributions should also exclude
`tasks/*/gold/**`, `third_party/upstream_designs/**`, `source_snapshot/**`, and
canary answer submissions. `tests/test_public_artifacts.py` enforces this public
build boundary.

Before republishing or redistributing full task packs, review the per-source
license fields and notices inside each pack. Sources marked unlicensed,
upstream-terms-only, noncommercial, or otherwise restricted should be handled
conservatively: obtain explicit permission, replace redistributed snapshots with
an acquisition script, or quarantine those reference artifacts from the public
full pack.

Do not claim ownership of upstream hardware designs. Cite upstream owners and
licenses for every task that uses a source-backed reference.
