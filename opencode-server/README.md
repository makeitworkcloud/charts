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
`openai/gpt-6-astra` without a variant override. The six Terra-tier subagents
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

Published standard OpenAI token rates are $10 per 1M input tokens and $50 per
1M output tokens for `gpt-6-astra`, versus $2 per 1M input and $10 per 1M
output for the prior `gpt-6-sol`
([gpt-6-astra](https://developers.openai.com/api/docs/models/gpt-6-astra),
[gpt-6-sol](https://developers.openai.com/api/docs/models/gpt-6-sol)). The
owner accepted this fivefold increase per token; it is not a claim about total
task cost, and no usage budget is implied. Chart CI is static validation and
proves neither account entitlement nor successful Responses tool calls. Before
any separately authorized rollout: confirm the deployed OpenCode version's
model catalog lists each new model, exercise each one with fresh-session tool
calls, and accept the resulting usage and cost; roll back only through a
separate GitOps chart pin revision.

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

The eight named primary agents (`makeitwork`, `xnoto`, `career`, `teacher`,
`grillmaster`, `homerepair`, `homesteader`, and `lawnmowerman`) carry a
self-contained session knowledge-read policy: on the first substantive task
in a fresh session that could rely on recalled agent-specific facts or
duplicate earlier research, they decide whether their knowledge home is
relevant, verify current access, read their own subset README through the
validated default-branch cache route or the GitHub verified-SHA fallback, and
then only the task-relevant documents it cites, reporting the knowledge home
as unavailable instead of assuming remembered facts; they recheck index and
provenance only when the task, context, or freshness changes, and write only
sparse, necessary, verified durable facts under the existing subset policy.
This is a policy-directed attempt, not a guaranteed automatic enforcement
mechanism; multiuser knowledge isolation and backup/restore automation
remain deferred.

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

## Memory pilot (opt-in)

`memoryPilot.enabled=true` switches a release from the production rendering to
an isolated memory pilot: the production ConfigMap and Deployment are suppressed
and the chart emits only a pilot ConfigMap and a single-replica `Recreate`
Deployment. Rendering is locked to the reviewed contract: `fullnameOverride`
must be exactly `opencode-memory-pilot`, `persistence.existingClaim` exactly
`opencode-memory-pilot-home`, and the pilot provider, server-auth, and embedding
Secret names exactly the pilot defaults; any other value, including the
production names, fails rendering. Chart 0.4.6 uses the pinned `opencode-mem`
plugin with remote OpenAI embeddings at `https://api.openai.com/v1`:
`text-embedding-3-small`, 1536 dimensions, task prefixes disabled, and
`embeddingApiKey: "env://OPENCODE_EMBEDDING_API_KEY"`. There is no custom image,
sidecar, or extraction-provider switch; the isolated
`zai-coding-plan/glm-5.3` provider still requires its own credential.

`memoryPilot.embeddingSecretName` must be exactly
`opencode-memory-pilot-embeddings`, with key `apiToken` injected only at runtime
as `OPENCODE_EMBEDDING_API_KEY`. Reloader watches all three pilot Secrets:
`opencode-memory-pilot-provider`, `opencode-memory-pilot-server-auth`, and
`opencode-memory-pilot-embeddings`. The owner encrypts the embedding Secret in
`kustomize-cluster` under the existing SOPS `apiToken` match; no plaintext
secret contents belong in configuration or Git, and no global OpenAI key
environment variable is needed. This embedding key never replaces production
OpenAI OAuth. The pilot mounts no production secrets, agents, skills, MCP
configuration, or artifact PVC.

Startup uses `/bin/sh -ec` to reject a missing, empty, or any-whitespace-containing
embedding key with a fixed message that never logs the key, then
`exec opencode web --hostname 0.0.0.0 --port 4096` with unchanged server arguments.
The guard prevents local fallback caused by empty configuration; it does not
prove API validity. Historical local ONNX writes failed; the pinned remote path
bypasses local model loading, but real HTTP memory write/search on the exact
image remains UNTESTED. npm dependencies still ship and install; neither package
removal nor blocked network access is claimed. Startup may perform billable
remote warmup, so even startup requires an approved paid-test scope.

`autoCaptureEnabled: false` is the initial setting, but the existing enabled
`chatMessage` path still persists raw SYNTHETIC prompts. The disabled web server
and profile settings remain unchanged. Existing 768-dimensional vector state
must not be silently reused or reset: inspect metadata and obtain separate
approval for migration or an empty store, with no automatic deletion.

The historical 0.4.0 baseline comparison permits the QA reviewer's existing
end-of-file correction and exactly seventeen approved model-header changes: the
nine primary agents' exact Terra-to-Astra model change with removal of
`variant: default`, the six Terra-tier subagents' exact Terra-to-Sol model-line
change with each variant preserved, and the two Luna-tier subagents' exact
Luna-to-GPT-6 model-line change, plus the eight named primary agents' exact
session knowledge-read policy paragraph inserted before one asserted per-file
anchor, plus the four Kimi subagents' exact model-prefix line updates from
`kimi-for-coding` to `kimi-code-plan-cn` and the three exact `opencode.json`
config-line substitutions — global fallback model, enabled-provider allowlist
entry, and provider key — each asserted to occur exactly once. All other agent
bytes and production render comparisons remain enforced. These changes affect
the production ConfigMap
checksum, so a normal production pod rollout on the chart version
pin can occur even when the pilot is disabled. See [Memory pilot](docs/memory-pilot.md)
for the baseline comparison contract.

The 0.4.6 remote-embedding change leaves production rendering unchanged from
0.4.5; the historical baseline comparison above remains in force. Versioned
publication may still trigger an automatic PRODUCTION pin pull request with
auto-merge enabled. Pilot version selection, Application registration, and manual
sync are independent, separately confirmation-gated actions, not consequences
of publishing the chart.

Operators must read [Memory pilot](docs/memory-pilot.md) before enabling it:
the pilot is single-replica persistence on a dedicated home claim with no
high-availability or node-loss protection. All three isolated credentials
(provider, server-auth, and embedding) are activation prerequisites.

Backup/restore automation and hardening remain deferred, with no node-loss
recovery guarantee. Any manual operator copy is scoped to plugin memory
inventory, database shards, and raw prompt records: classify content first,
exclude `.auth-token`, `auth.json`, and all other credentials unconditionally,
and never export the whole home. OpenCode's session database shares the home
PVC but is outside the plugin backup scope.

## Delivery lifecycle

1. Open a charts pull request and require repository hygiene, Helm validation, and package checks to pass.
2. Merge only with explicit confirmation. The main workflow publishes the immutable OCI chart to `ghcr.io/makeitworkcloud/charts/opencode-server`.
3. After publication, charts automation opens or updates a `kustomize-cluster` pull request changing the OpenCode Application's pinned `targetRevision` and enables GitHub auto-merge.
4. Treat that pull request as a separate desired-state change gated by `kustomize-cluster` required checks. Its creation does not deploy or sync Argo CD.
5. After the GitOps pin merge, verify the `gitops-workloads` root, `opencode` child Application, Deployment rollout, pods, events, and representative OpenCode behavior.

### Historical 0.1.75 aggregate cutover

Version 0.1.75 paired with the former `kustomize-cluster` gateway-member rename and is retained only as historical rollout context. The current direct-proxy design supersedes that aggregate route: OpenCode must use the direct client URLs in `files/opencode.json`, and `vmcp-gateway` must remain external-only.

See the repository guides in `docs/adding-a-chart.md` and `docs/gitops-update-automation.md`, plus the `kustomize-cluster` adding-workload and rollout guides.
