# Release License Triage

EDA Bench full task packs contain upstream hardware snapshots. Runtime task
packs contain only prompts and metadata, but the full packs still need a clean
redistribution story before a NeurIPS release.

Use this policy before publishing a new task-pack revision:

| Source status | Release action |
|---|---|
| OSI, CERN OHL, TAPR OHL, Solderpad, or Creative Commons license compatible with redistribution | Keep the full snapshot and license notice |
| License exists but attribution/share-alike/source obligations are nontrivial | Keep only after the full pack includes the required notice and source pointer |
| Upstream terms only or no standalone license file | Get explicit permission, replace the full snapshot with an acquisition script, or quarantine from the public full pack |
| Noncommercial or otherwise restricted source | Keep out of the public benchmark unless the restriction is compatible with the intended release |

For every released task, the full pack should record:

- upstream URL and commit or release identifier;
- source owner;
- license label;
- local license or notice path;
- whether the reference artifact is redistributed or acquired by script;
- any attribution or share-alike obligations.

The paper and data card should identify the exact task-pack revision after this
triage. If tasks are quarantined, report both the original candidate count and
the released score-supported count.

## Current Risk Inventory

The original source catalog recorded 40 candidate source-backed tasks. The
released public manifest quarantines the following five tasks from full-pack
redistribution until permission or acquisition-script replacement is available:

| Task | Recorded source license | Conservative release action |
|---|---|---|
| `cm5io_official` | Upstream terms / no standalone license file | Obtain permission, replace the vendored snapshot with an acquisition script, or quarantine from the public full pack |
| `mixed_signal_stm32_dev_board` | Unlicensed upstream snapshot | Obtain permission, replace the vendored snapshot with an acquisition script, or quarantine from the public full pack |
| `rp2350b_dev_board` | Unlicensed upstream snapshot | Obtain permission, replace the vendored snapshot with an acquisition script, or quarantine from the public full pack |
| `stm32f_audio_codec` | Unlicensed upstream snapshot | Obtain permission, replace the vendored snapshot with an acquisition script, or quarantine from the public full pack |
| `ef28_badge` | CC BY-NC-SA 4.0 | Quarantine unless the intended public release and downstream use policy are compatible with the noncommercial restriction |

The conservative public full-pack release has 35 redistributable tasks. The
paper may describe the 40-task candidate set as validation history, but the
artifact availability statement must identify the 35-task public release and the
five quarantined task references.

Runtime packs contain prompts and metadata rather than upstream snapshots, so
quarantine applies to full-pack redistribution of references, source snapshots,
and canaries. It does not require removing the task id from code, manifests, or
runtime metadata when the paper clearly reports the artifact split.
