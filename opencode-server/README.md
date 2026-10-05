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

The ten primary agents (`default`, `makeitwork`, `xnoto`, `career`, `teacher`,
`grillmaster`, `homerepair`, `homesteader`, `lawnmowerman`, and `mechanic`)
select `openai/gpt-6.1-sol` without a variant override. The six Terra-tier subagents
(`terra`, `adversarial-code-reviewer`, `cloud-architecture-reviewer`,
`devops-engineer`, `infra-security-reviewer`, and `recruiter-resume-reviewer`)
select `openai/gpt-6-sol`, and the two Luna-tier subagents (`luna` and
`qa-engineer`) select `openai/gpt-6-luna`; existing variants are preserved. The
GLM and MiniMax subagents are unchanged. `opencode models openai` checks the model
catalog; use `opencode models openai --refresh` if a model is absent. Catalog
presence does not prove provider entitlement or successful inference. After an
approved rollout, verify the changed models in a fresh session; existing
sessions may retain their selected model. Configuration is loaded at server
startup, not hot-reloaded.

Pricing and account entitlement for `gpt-6.1-sol` have not been verified for
this change. No token rates, relative savings, or total task-cost claims are
made, and no usage budget is implied. Chart CI is static validation and proves
neither model availability, account entitlement, nor successful inference or
Responses tool calls. Before any separately authorized rollout, confirm that
the deployed OpenCode version's model catalog lists `openai/gpt-6.1-sol`,
verify account entitlement and current pricing, and accept the resulting usage
and cost. Fresh-session inference and tool-call checks remain required after
rollout; roll back only through a separate GitOps chart pin revision.

### Kimi provider-id migration

The four Kimi subagents (`kimi`, `kimi-256k`, `docs-writer`, and
`release-engineer`) and the global fallback model now select the
`kimi-code-plan-cn` provider id. Upstream renamed `kimi-for-coding` to
`kimi-code-plan-cn` for the same `api.kimi.com` endpoint and created a
separate global Kimi provider
([models.dev commit](https://github.com/anomalyco/models.dev/commit/ae065079d839cd1e4d824007aa8acef87ff5465f));
selecting that separate global provider would be its own owner decision
requiring confirmation of the appropriate account. The chart migration changes only ids: the
`files/opencode.json` global fallback model, enabled-provider allowlist entry,
and provider key, plus the four agent model prefixes. Model suffixes (`k3` and
`k3-256k`), variants, prompt bytes, the `{env:KIMI_API_KEY}` reference, and the
`opencode-kimi` Secret wiring are unchanged, and no custom SDK, base URL, or
model definition is introduced. The upstream catalog migration also switches
the provider from the Anthropic protocol to the OpenAI-compatible protocol,
so the preserved endpoint and model ids do not prove identical wire behavior;
fresh-session inference and tool-call smoke tests remain a rollout gate.
Chart CI is static validation, not inference.
After a confirmed rollout, check that the deployed OpenCode model catalog lists
the `kimi-code-plan-cn` keys, then verify fresh-session inference and tool
calls.

The `devops-engineer` subagent is a parent-directed, read-only reviewer for supplied DESIGN proposals and completed CHANGE diffs covering CI, workflows, artifacts, GitOps handoffs, runners, and delivery integration. It uses `openai/gpt-6-sol` with the default model configuration and denies all native and MCP tools through a wildcard permission deny; it does not implement, dispatch, publish, merge, or mutate live systems.

### Cloud architecture design review

The `cloud-architecture-reviewer` subagent ([`files/agents/cloud-architecture-reviewer.md`](files/agents/cloud-architecture-reviewer.md)) is a supplied-evidence, preimplementation design critic for new cloud services or material changes to service selection, topology, state placement, recovery, scaling, or recurring cost. It uses `openai/gpt-6-sol` with the default variant and denies all native and MCP tools through a wildcard permission deny, so it reviews only the parent-supplied design brief and evidence.

The review is requirements-led and simplicity-biased: it prefers established vendor- or canonical-owner-maintained solutions, challenges unsupported complexity, and no cloud vendor is preferred by default. The five code-capable primary agents (`default`, `makeitwork`, `xnoto`, `career`, `teacher`) route material designs to it with a compact design brief and skip routine changes within an established pattern; the existing pre-pull-request review gates are unchanged, and this design review does not replace them.

`ADVANCE` means the design is reasonable to begin implementing — not approval, authorization, deployment, health, or functional verification. The reviewer does not automatically request a higher variant or a second reviewer, and model comparisons such as Kimi remain deferred with no savings benchmark claimed. CI validates packaging and instruction contracts, not review quality; after a separately approved rollout, a fresh session should verify the agent inventory, tool denial, and representative review cases as described in [Agent instruction architecture](docs/agent-instruction-architecture.md).

### Mechanic agent

The `mechanic` primary agent
([`files/agents/mechanic.md`](files/agents/mechanic.md)) is a lifestyle
primary for owner-assisted car and truck maintenance and diagnostics. It
identifies the vehicle through owner-confirmed VIN transcription and build
facts (year, market, build date, engine, transmission, drivetrain, and
modifications), keeps photo observations separate from hypotheses and never
declares roadworthiness from a photo, applies safety triage first
(stop-driving and tow conditions), sources specifications and procedures from
official OEM documentation first with recorded applicability and respect for
licensed documentation rights, and keeps the full VIN private to the vehicle
record — never in filenames, commits, pull requests, logs, or general web
searches. High-voltage hybrid/EV and airbag/pretensioner work is
professional-only, and brakes, steering, fuel, structural, refrigerant, and
ADAS work defers to qualified service when tools, training, or documentation
are missing. It advises on vehicles only and does not author cloud
infrastructure, chart, or workflow changes. Like the other lifestyle
primaries it carries no pre-pull-request review gate.

The mechanic knowledge home is the private `docs/agents/mechanic/` subset in
`makeitworkcloud/agent-knowledge` (vehicles registry, per-vehicle records,
per-task procedures, and templates). That subset is authored separately and
is a prerequisite for knowledge-backed operation: the agent verifies private
access rather than assuming it from cache presence, and reports the knowledge
home as unavailable instead of assuming remembered facts.

CI statically validates packaging and the instruction contract only. After a
separately approved rollout, verify manually in a fresh session: the agent is
selectable; it reads its subset README and the relevant vehicle record before
owner-specific advice; it opens with safety triage on stop-driving symptoms;
it refuses to judge roadworthiness from a photo; it requires owner
confirmation of a VIN transcription; it separates observations from
hypotheses; it cites OEM sources with applicability; and it keeps photos and
the full VIN off external services without destination-specific consent and
off public-safe surfaces.

### MCP routing

`files/opencode.json` configures OpenCode as a direct in-cluster MCP client. Each integration connects to its own cluster-local ToolHive proxy Service in the `mcp` namespace; the configured client URLs are canonical. Direct tool names do not use the `makeitwork_` aggregate prefix. The `vmcp-gateway` VirtualMCPServer is reserved for external consumers and must not be configured as an OpenCode client.

`agent-pipe` remains a direct chart-local service. The other direct clients include `github`, `hero-ssh`, and `codebase-memory`, together with the configured ToolHive backend proxies. Do not add duplicate aggregate and direct entries, because duplicate tool namespaces make tool selection ambiguous.

### Cloudflare API MCP

`cloudflare` reaches the in-cluster ToolHive read-only remote proxy through its direct OpenCode ClusterIP client. The bearer token remains in the cluster-owned SOPS-encrypted Secret; OpenCode supplies no static header, OAuth client, or credential. The `vmcp-gateway` is external-only; external gateway callers authenticate with the shared Cloudflare Access service token, never the Cloudflare API token, which the direct proxy injects only on outbound upstream requests.

Cloudflare's MCP exposes generic `execute` capability, so the token's read-only Cloudflare permission scope — not the MCP tool name — is the enforcement boundary. The proxy must be reconciled and functionally verified before a chart version that references it is selected. Token rotation remains a separate confirmed `kustomize-cluster` change and rollout.

## Living knowledge

Mutable repository lifecycle, topology, generated-file ownership, and producer-consumer guidance belongs in the private `makeitworkcloud/agent-knowledge` repository rather than immutable chart content. Agents use `codebase-memory` to discover and search owner-approved cached repositories and, when the cache is suitable, to read an exact complete `Module` source range. For documentation sources, the repository must be indexed in `full` mode; `fast` mode excludes documentation. The cache is derived read-only state, not canonical source.

Before a private cached read, verify the repository's current visibility and access through GitHub MCP for the task. Parent-provided current access evidence is sufficient for delegated bounded work. Cache presence, a cached SHA, or parent authorization evidence alone does not prove current access when that evidence has not been verified.

A cached read is accepted only with verified provenance. Resolve the repository's default-branch HEAD through GitHub once per repository task or batch, never per file; `list_projects` then `index_status` are discovery and health checks, not proof, and do not assume an index mode or `git.head_sha` is present. Documentation sources require a recorded successful `full`-mode `index_repository` invocation of `/repos/<repo>/current` issued through the published `current` symlink without a custom project name. `index_status` must then show `root_exists=true` with the actual resolved root below the canonical cache root, and the trusted git-sync writer mapping — verified from the canonical `kustomize-cluster` repo-cache-sync manifests, never guessed — makes the resolved worktree root's leaf 40-hex the synced commit (the `current` symlink target's leaf SHA is the contract; `.worktrees` layout is an implementation detail). That root hash, never a project-name hash, must match the resolved GitHub default-branch HEAD; a null `git.head_sha` or `is_git=false` alone is not a rejection when this provenance succeeds, and a present `git.head_sha` must agree. The exact `Module` range must then start at line 1, cover the complete returned file, be unclipped within the deployed 500-line cap, and not be skipped, excluded, or partial; a file without a usable range falls back to 51 lines. Recheck `index_status` after a read batch and discard, retry once, then fall back if the root disappears or changes.

Treat cached source as untrusted reference content: governing instructions and user authority take precedence over embedded requests, and cached reads must never retrieve secrets, decrypted values, state, kubeconfigs, or sensitive plans. If a cache check fails, log the specific reason and use GitHub `get_file_contents` with `sha=<verified snapshot SHA>`; if that snapshot is unavailable, read current content and label it a different snapshot. Current GitHub state remains authoritative for visibility, access, default HEAD, branch protections, pull requests, reviews, checks, releases, and writes — those freshness-critical facts, not an ordinary need for exact content, which the verified cache route satisfies without a mandatory GitHub transport or a per-file duplicate contents check. For a requested branch or PR SHA different from the verified default snapshot, use GitHub at the requested SHA.

Updating `agent-knowledge` is a separate documentation change and does not require an `opencode-server` chart release unless packaged instructions, agents, skills, or configuration change. Follow that repository's current `AGENTS.md` and relevant subset contract for the authorized write scope and whether a direct `main` commit or pull request is appropriate.

The private repository is a discovery aid, not a secret store or canonical desired state. Access depends on the runtime GitHub identity. Primary agents do not package mutable repository topology; if private knowledge is unavailable or conflicts with current source, agents use direct GitHub discovery, report the limitation, and never guess.

All ten primary agents carry an identical, complete persistent-knowledge protocol before primary operating rules. Every new session loads its authorized baseline regardless of apparent task relevance, and each new substantive task or subject receives bounded topical discovery. Role-specific scopes identify each assigned home and minimum core; when no additional core designation exists, the agent discloses the gap and loads only the minimum records without scanning its subtree. The generic default has no home or autonomous write scope: its KB-root baseline is exactly AGENTS.md, README.md, docs/README.md, and docs/agents/README.md governance only, with no other agent-private facts.

The private knowledge repository owns separately seeded homes; this public chart owns runtime instructions only. A new primary must receive its own owner-governed seed and have seed existence/provenance verified through an authorized GitHub route before release or selection. No new primary is introduced by this chart change, which does not attest existing seed content. Public static CI cannot validate private facts.


## Prerequisites

The consuming cluster supplies:

- the existing OpenCode home PVC;
- a separate artifact PVC named through `persistence.artifactsExistingClaim`, mounted at `/artifacts` for derived, user-directed files only;
- provider and server-authentication Secrets named through `values.yaml`;
- the Service and external `TunnelBinding`;
- access to the direct in-cluster MCP proxy Services configured in `files/opencode.json`.

SlideSpeak is consumed through its direct in-cluster proxy client. Its API key is held only in the SOPS-encrypted `kustomize-cluster` Secret injected on that remote-proxy member; OpenCode does not store it and does not complete provider OAuth. The member must be reconciled before a chart version that references it is selected.

Never put credentials, decrypted values, kubeconfigs, private keys, or tokens in chart files or values.

## OpenAI OAuth seed rotation

The cluster-owned `opencode-openai-auth` Secret may contain an optional,
non-sensitive `auth-seed-revision` key alongside its encrypted `auth.json`.
The init container records that revision on the persistent home PVC and replaces
`auth.json` atomically only when the revision changes or no credential exists.
This preserves OAuth refresh-token rotation across ordinary pod restarts.

The Deployment opts into Reloader for that named Secret. The consuming cluster
must configure Reloader to watch the `opencode` namespace. During an intentional
credential rotation, update the encrypted `auth.json` and increment
`auth-seed-revision` in the same GitOps revision. Do not add the revision until
a fresh credential is ready: a revision change deliberately replaces the
persisted OAuth grant.

## Rendered resources

- Deployment with an init container that seeds immutable chart configuration into an `emptyDir`
- ConfigMap containing OpenCode configuration, agents, and skills

The chart mounts the cluster-owned artifact PVC only into the OpenCode container. The independent `agent-pipe-uploader` chart mounts that PVC read-only and has no AWS credentials; it exposes the cluster-internal presigned-upload API for explicit, user-approved artifact delivery.

Configuration is loaded when OpenCode starts. A reconciled chart update replaces the pod through the ConfigMap checksum annotation; it is not hot-reloaded into an existing process.

## OpenCode v2 migration

Chart 0.5.0 moves production from OpenCode `1.18.29` to `2.0.22`. This is a
major upstream upgrade with deliberate production downtime: the Deployment
becomes single-replica `Recreate`, so the cutover is a full stop, and
owner-approved session preservation and outage acceptance are prerequisites.
Production serves with `opencode serve --hostname 0.0.0.0 --port 4096` (the
upstream v2 replacement for `web`), sets `OPENCODE_DB=opencode.db` explicitly
matching the existing home-relative database path, and relies on upstream
`OPENCODE_PASSWORD` falling back to the existing `OPENCODE_SERVER_PASSWORD`
environment variable ([`env.ts`](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/cli/src/env.ts));
the server process suppresses its generated-password print when the variable
is set ([`server-process.ts`](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/cli/src/server-process.ts)).
The v1-to-v2 storage migration is upstream's
[`v1-migration.bun.ts`](https://github.com/anomalyco/opencode/blob/527f0b931d1f9b3ebd34e106c51b31ce5db5b075/packages/core/src/database/v1-migration.bun.ts).
No runtime or image is introduced beyond the stock upstream image. The v1
configuration format remains supported by v2 and is kept as-is; native v2
configuration conversion is optional and deferred to a separate change.

### Owner decision for this cutover (2026-10-02)

For this 0.5.0 cutover the owner explicitly approved the rollout and waived
the pre-merge database backup and isolated restore verification gates ("No
backup necessary; go forth", confirmed "understood and waived"). There is no
verified recovery guarantee for this release: the v1-to-v2 session migration
may fail irreversibly, and an image downgrade against a v2-mutated database
is not a rollback. The owner authorized the maintenance-window `Recreate`
cutover and rollout under the current Application's automated sync —
serialized by the single-replica `Recreate` strategy, with no manual Argo CD
sync pause or drain step — and accepts the disclosed unknown OAuth
seed-rotation behavior under v2 (the v2 credentials import may be one-time,
so seed-revision replacement of `auth.json` after the v2 migration is
unverified and is not a gate for this owner-approved release).

### Publication coordination

- Merging to `main` publishes the immutable OCI chart. The pre-existing draft
  `kustomize-cluster` pull request on branch
  `automation/opencode-server-0.5.0` must contain both the chart pin and the
  protocol 2 (`OPENCODE_API_VERSION=2`) exporter change before this chart
  merges, so the pin and the exporter change land together.
- The update automation is unchanged: it finds the existing branch and its
  draft pull request. The draft state prevents auto-merge until the published
  artifact exists and CI is green; requesting auto-merge for a draft may fail
  the post-publication updater job, and that does not invalidate an already
  published chart.
- This chart change performs no live operation; rollout sequencing is the
  GitOps pin merge described in the delivery lifecycle.

### Backup and restore recommendations

The following remain recommended practice for OpenCode upgrades generally.
For this owner-approved 0.5.0 release they are waived per the owner decision
above and are not merge gates:

- Stop the v1 writer through a separately authorized operation before any
  backup; quiescing sessions alone does not make a live database copy
  consistent.
- With the writer stopped, take a consistent offline SQLite backup or a
  storage snapshot of the OpenCode database. Copying a live `opencode.db`
  (including its `-wal`/`-shm` companions) while a writer may still be
  running is not a consistent backup. Exclude `auth.json` and every other
  credential in the home directory; any backup location must be an approved
  sensitive-data recovery location, never the artifacts PVC or the S3 user
  file-delivery path.
- Verify an isolated restore, the v2 migration status, and representative
  preserved sessions. A healthy TCP probe is not migration success.
- Never downgrade the image against a database already mutated by v2.
  Sessions created by v2 after cutover require a separate recovery decision
  if rollback is needed.

### Post-rollout verification

After a separately authorized rollout, verify provider authentication and
inference, permission rules, and MCP connectivity in a fresh session. Static
chart CI proves none of these.

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
embedding endpoint, and no new images beyond the historical v1 image pinned
separately through `memoryPilot.image` — while OpenCode serves port 4096 behind
the cluster-owned Service. Local embedding runtime compatibility on the stock
image is an unverified activation gate. The pilot mounts no production
secrets, agents, skills, MCP configuration, or artifact PVC.

Version split: the production Deployment runs the pinned OpenCode v2 image
from `image`, while the pilot remains on the historical v1 image
`1.18.29@sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8`
pinned independently through `memoryPilot.image` and keeps its v1 `web` args.
The production v2 pin does not alter the pilot render, and this split does
not activate, migrate, or repair the disabled pilot experiment.

The historical 0.4.0 baseline comparison permits the QA reviewer's existing
end-of-file correction and exactly seventeen approved model-header changes: the
nine primary agents' exact `openai/gpt-5.6-terra` to `openai/gpt-6.1-sol`
model change with removal of
`variant: default`, the six Terra-tier subagents' exact Terra-to-Sol model-line
change with each variant preserved, and the two Luna-tier subagents' exact
Luna-to-GPT-6 model-line change; it also permits the ten-primary runtime protocol and scope migration; the
historical render fixture adopts those explicitly enumerated prompts, while a
pinned-base regression check preserves every post-operating-rules byte, and
the homesteader confidentiality/workflow substitutions, plus the four Kimi subagents' exact model-prefix line updates
from `kimi-for-coding` to `kimi-code-plan-cn` and the three exact
`opencode.json` config-line substitutions. In addition, the comparison permits
exactly one approved new agent file, `files/agents/mechanic.md`, absent from
the historical baseline: the test asserts its absence in the extracted
baseline and copies the current chart source in after the historical
transforms. The historical counts above are unchanged; the mechanic agent did
not exist in the historical baseline. In addition, the comparison permits
exactly four approved production runtime changes applied to the extracted
baseline before rendering: the production `values.yaml` image tag asserted
exactly once and replaced from
`1.18.29@sha256:ecc3bf96ee55dad226d9cde50d79aaa8a1215c47860c0fcdc71570461bf438b8`
to `2.0.22@sha256:11f2b6c96d380867387fbee390c06cb47efffd9fdc37009b4cd40795b45dad19`,
the production Deployment container args change from `web` to `serve`, the
added single-replica `Recreate` strategy, and the explicit
`OPENCODE_DB=opencode.db` environment entry; the pilot image is pinned
separately and is not part of the production baseline render. Non-primary agent bytes remain identical to the historical fixture; primary source-to-ConfigMap byte parity and chart-archive parity remain exact, while a pinned-base check protects every primary operating-rules tail. These changes affect the
production ConfigMap checksum, so a normal production pod rollout on the
chart version pin can occur even when the pilot is disabled. See
[Memory pilot](docs/memory-pilot.md) for the baseline comparison contract.

Operators must read [Memory pilot](docs/memory-pilot.md) before enabling it:
the pilot is single-replica persistence on a dedicated home claim with no
high-availability or node-loss protection, and backup and restore automation
is deferred.

## Delivery lifecycle

1. Open a charts pull request and require repository hygiene, Helm validation, and package checks to pass.
2. Merge only with explicit confirmation. The main workflow publishes the immutable OCI chart to `ghcr.io/makeitworkcloud/charts/opencode-server`.
3. After publication, charts automation opens or updates a `kustomize-cluster` pull request changing the OpenCode Application's pinned `targetRevision` and enables GitHub auto-merge.
4. Treat that pull request as a separate desired-state change gated by `kustomize-cluster` required checks. Its creation does not deploy or sync Argo CD.
5. After the GitOps pin merge, verify the `gitops-workloads` root, `opencode` child Application, Deployment rollout, pods, events, and representative OpenCode behavior.

### Historical 0.1.75 aggregate cutover

Version 0.1.75 paired with the former `kustomize-cluster` gateway-member rename and is retained only as historical rollout context. The current direct-proxy design supersedes that aggregate route: OpenCode must use the direct client URLs in `files/opencode.json`, and `vmcp-gateway` must remain external-only.

See the repository guides in `docs/adding-a-chart.md` and `docs/gitops-update-automation.md`, plus the `kustomize-cluster` adding-workload and rollout guides.

## Primary persistent knowledge contract

All ten primary runtime files contain the same complete protocol and scoped home contract directly; this is intentional prompt duplication, not build-time inheritance. The default is the maintainer's starting point, not an inheritance path.

For named homes, the subset README, scope/authority/source-constraints records, and mandatory entry records form the minimum current core. Follow any additional baseline they expressly designate; otherwise disclose the designation gap, load that minimum, and do not scan the subtree. Default has no own home: the KB-root shared baseline is exactly AGENTS.md, README.md, docs/README.md, and docs/agents/README.md governance only. It does not authorize access to another agent's private records.

The knowledge repository owns seeds; this chart owns runtime instructions. New primaries require separate verified owner-governed seeds before release or selection and cannot borrow another agent's home. Private corpus content is never copied into this public chart or CI; public static CI cannot verify private seed facts. No new primary or seed is introduced by this change. Root AGENTS.md remains universal safety and repository routing, not KB lifecycle policy.

Static CI checks protocol/scope wording, render parity, and archive packaging; it does not establish runtime behavior. The existing fresh-session matrix remains future validation work. Delivery remains staged: chart change, published OCI artifact, automatic GitOps pin PR, separate root/child reconciliation and health, then functional verification.
