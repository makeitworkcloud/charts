# OpenCode server chart

Helm chart for the shared Make IT Work Cloud OpenCode web server and its non-secret global configuration.

## Ownership

This chart owns the OpenCode Deployment and chart-packaged non-secret configuration. `makeitworkcloud/kustomize-cluster` owns the consuming Argo CD Application, namespace integration, persistent storage, Services, TunnelBinding, and SOPS-encrypted Secrets.

Every Kubernetes object has one owner. Do not duplicate cluster-owned resources in this chart.

## Packaged configuration

The chart copies these immutable package inputs into `/home/opencode/.config/opencode` at pod startup:

- `files/opencode.json` — providers, enabled MCP integrations, default agent, and global OpenCode configuration
- `files/AGENTS.md` — shared instructions loaded by every agent, including the compact common repository routing floor
- `files/agents/*.md` — owner-specific primary agents, the generic `terra` execution subagent, model-backed subagents for delegated passes, and specialized read-only SDLC subagents (adversarial code review, cloud architecture design review, DevOps integration and delivery review, QA coverage and documentation adequacy, release readiness, infrastructure security, documentation drafting)
- `files/skills/*/SKILL.md` — specialized operational workflows

A change to any packaged file is chart content and requires a new `Chart.yaml` version. See [Agent instruction architecture](docs/agent-instruction-architecture.md) for the primary-agent, subagent, and shared-instruction design.

The nine primary agents (`default`, `makeitwork`, `xnoto`, `career`, `teacher`,
`grillmaster`, `homerepair`, `homesteader`, and `lawnmowerman`) select
`openai/gpt-6-sol` without a variant override. Subagent model selections and the
global fallback model are unchanged. `opencode models openai` checks the model
catalog; use `opencode models openai --refresh` if the model is absent. Catalog
presence does not prove provider entitlement or successful inference. After an
approved rollout, verify the model in a fresh session; existing sessions may
retain their selected model. Configuration is loaded at server startup, not
hot-reloaded.

The `devops-engineer` subagent is a parent-directed, read-only reviewer for supplied DESIGN proposals and completed CHANGE diffs covering CI, workflows, artifacts, GitOps handoffs, runners, and delivery integration. It uses `openai/gpt-5.6-terra` with the default model configuration and denies all native and MCP tools through a wildcard permission deny; it does not implement, dispatch, publish, merge, or mutate live systems.

## Memory pilot (opt-in)

`memoryPilot.enabled=true` switches a release from the production rendering to
an isolated memory pilot: the production ConfigMap and Deployment are suppressed
and the chart emits only a pilot ConfigMap and a single-replica `Recreate`
Deployment. Rendering is locked to the reviewed contract: `fullnameOverride`
must be exactly `opencode-memory-pilot`, `persistence.existingClaim` exactly
`opencode-memory-pilot-home`, and the pilot provider and server-auth Secret
names exactly the pilot defaults; any other value, including the production
names, fails rendering. The pilot runs OpenCode with only the pinned
`opencode-mem` plugin and its local ONNX embeddings — no sidecar, no remote
embedding endpoint, and no new images — while OpenCode serves port 4096 behind
the cluster-owned Service. Local embedding runtime compatibility on the stock
image is an unverified activation gate. The pilot mounts no production
secrets, agents, skills, MCP configuration, or artifact PVC.

The historical 0.4.0 baseline comparison has two approved agent changes: a
repository-hygiene end-of-file correction to `files/agents/qa-engineer.md`,
and the nine primary agent files (`career.md`, `default.md`, `grillmaster.md`,
`homerepair.md`, `homesteader.md`, `lawnmowerman.md`, `makeitwork.md`,
`teacher.md`, and `xnoto.md`) move from `openai/gpt-5.6-terra` with
`variant: default` to `openai/gpt-6-sol` with no variant. The parity test
applies those exact frontmatter changes to the extracted historical baseline;
all other source and rendered equality checks remain unchanged. These approved
changes can change the rendered production ConfigMap checksum relative to the
published 0.4.0 chart, and a normal production pod rollout on the chart version
pin can occur even when the pilot is disabled. See [Memory pilot](docs/memory-pilot.md)
for the complete baseline comparison contract.

Operators must read [Memory pilot](docs/memory-pilot.md) before enabling it:
the pilot is single-replica persistence on a dedicated home claim with no
high-availability or node-loss protection, and backup and restore automation
is deferred.
