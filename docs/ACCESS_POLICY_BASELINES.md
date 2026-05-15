# Access-Policy Baselines

EDA Bench evaluates web-enabled agents under a fixed public-source access
policy. Access policy is therefore a benchmark condition, not an incidental
detail.

Use this matrix when preparing NeurIPS tables, leaderboard entries, or release
notes.

| Baseline | Web | Reference/full pack | Oracle access | Purpose |
|---|---|---|---|---|
| Default web agent | Enabled | Not mounted | No grader internals in runtime | Measures public-source task solving under the released access policy |
| No-web agent | Disabled | Not mounted | No grader internals in runtime | Separates KiCad/tool competence from public-source retrieval; six completed full no-web sweeps are available in HF provenance |
| Retrieval/copy upper bound | Enabled | Upstream discovery or explicit upstream project path allowed | No grader internals in runtime | Estimates the score ceiling when source discovery succeeds |
| Oracle-aware repair | Usually disabled after initial attempt | Final project only | Grader feedback allowed between repair iterations | Tests whether low scores come from repair-loop weakness rather than impossible tasks |
| Human/expert sample | Engineer-controlled | Document exact reference access | Grader used only for scoring | Calibrates whether oracle scores agree with engineering judgment |

Before reporting comparisons, record:

- task-pack revision;
- runtime Docker image digest;
- whether web search was enabled;
- whether the full task pack or upstream source path was visible;
- whether grader outputs were exposed during the attempt;
- model and harness versions;
- token, cost, and provenance accounting.

Default leaderboard results should not be mixed with no-web, retrieval/copy, or
oracle-aware repair scores unless the access policy is shown in the table.

## Submission-Time Controls

The NeurIPS submission should use the completed no-web provenance rows already
available in Hugging Face. Do not block artifact release on an incomplete
expensive no-web matrix. If only a partial no-web sweep exists for a config,
omit it or report it as a calibration note, not as a full leaderboard row. The
comparison is useful when the task list, model, reasoning effort, Docker image,
task-pack revision, and grader revision match the web-enabled rows.

For a compact reviewer-facing table, use these groups:

| Group | Minimum useful result | How to interpret |
|---|---|---|
| Web-enabled baseline | Full 35-task released sweep | Primary released benchmark result |
| No-web calibration | Any completed full-harness sweep; otherwise a clearly labeled task subset | Measures how much public-source access changes the same harness |
| Retrieval/copy upper bound | A small audited sample is acceptable for submission | Demonstrates that references can score high when source discovery and translation are solved |
| Expert sanity check | One to five manually inspected task/reference scores | Checks whether the oracle agrees with engineering judgment on obvious pass/fail cases |

Do not present pending runs as results. If a run is still active at submission
time, cite it only as ongoing artifact work or omit it from the paper table.

Completed full no-web rows currently available in provenance:

| Harness | Weighted score | Unweighted score | Build successes |
|---|---:|---:|---:|
| Codex GPT-5.5 no-web medium | 0.0000 | 0.0000 | 0/35 |
| Codex GPT-5.5 no-web high | 0.0000 | 0.0000 | 0/35 |
| Codex GPT-5.5 no-web xhigh | 0.0000 | 0.0000 | 0/35 |
| Codex GPT-5.4 no-web xhigh | 0.0000 | 0.0000 | 0/35 |
| Codex GPT-5.4-mini no-web medium | 0.0000 | 0.0000 | 0/35 |
| Codex GPT-5.4-mini no-web high | 0.0000 | 0.0000 | 0/35 |
