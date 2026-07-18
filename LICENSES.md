# EDA-bench licensing and redistribution notes

EDA-bench tasks are based on upstream hardware projects with mixed licenses. The benchmark does not transfer ownership of those projects.

Each native Harbor task records its upstream repository, pinned commit, and license in `dataset/<task_id>/task.toml`. Its reference KiCad project lives at `dataset/<task_id>/solution/reference/` and is copied only into the shared verifier image, never the evaluated agent environment.

Before publishing or redistributing a task through the Harbor registry, review its `source_license` metadata and embedded reference project at:

```text
dataset/<task_id>/solution/reference/
```

Some upstream projects use permissive, copyleft, open-hardware, Creative Commons, or project-specific terms. Preserve required notices and attribution. Do not publish a task whose upstream terms do not permit redistribution of its embedded reference project.

The papers, reports, and benchmark wrappers remain governed by their own repository notices. Generated agent submissions remain subject to the policies and terms of the model, agent, and upstream material used to produce them.
