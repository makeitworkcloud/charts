# Memory pilot

Opt-in isolated rendering of `opencode-server` for the Make IT Work Cloud
memory pilot. Enabling it is a deployment-mode switch, not an additive
feature: one Application renders either production or the pilot, never both.

## Baseline and checksum parity

The pilot tests compare the production render against the historical 0.4.0
baseline commit `32a6b91` plus two explicitly approved, comparison-only
changes: the baseline `files/agents/qa-engineer.md` lacks a final newline and
the nine primary agent files (`career.md`, `default.md`, `grillmaster.md`,
`homerepair.md`, `homesteader.md`, `lawnmowerman.md`, `makeitwork.md`,
`teacher.md`, and `xnoto.md`) change from `openai/gpt-5.6-terra` with
`variant: default` to `openai/gpt-6-sol` with no variant. The test applies
those exact frontmatter changes to the extracted baseline before rendering;
all other bytes and source/render equality checks remain unchanged.
Because these approved changes include the QA formatting correction and the
nine primary model updates, the rendered production ConfigMap checksum can
differ from the published 0.4.0 chart, and a normal production pod rollout
on the chart version pin can occur even when the pilot is disabled. No claim
is made that the current production manifest or checksum exactly matches the
original baseline.
