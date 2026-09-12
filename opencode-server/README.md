# OpenCode server chart

Helm chart for the shared Make IT Work Cloud OpenCode web server and its non-secret global configuration.

## Ownership

This chart owns the OpenCode Deployment and chart-packaged non-secret configuration. `makeitworkcloud/kustomize-cluster` owns the consuming Argo CD Application, namespace integration, persistent storage, Services, TunnelBinding, and SOPS-encrypted Secrets.

Every Kubernetes object has one owner. Do not duplicate cluster-owned resources in this chart.

## Packaged configuration

The chart copies these immutable package inputs into `/home/opencode/.config/opencode` at pod startup:

- `files/opencode.json` — providers, enabled MCP integrations, default agent, and global OpenCode configuration
- `files/AGENTS.md` — shared instructions loaded by every agent
- `files/agents/*.md` — owner-specific primary agents, model-backed subagents for delegated passes, and specialized read-only SDLC subagents (adversarial code review, QA coverage and documentation adequacy, release readiness, infrastructure security, documentation drafting)
- `files/skills/*/SKILL.md` — specialized operational workflows

A change to any packaged file is chart content and requires a new `Chart.yaml` version. See [Agent instruction architecture](docs/agent-instruction-architecture.md) for the primary-agent, subagent, and shared-instruction design.

### MCP routing

`files/opencode.json` routes integrations through a single internal gateway aggregate entry, `makeitwork` → `http://vmcp-gateway.mcp.svc:4483/mcp` (`kustomize-cluster` `workloads/mcp-gateway`). Aggregate tools arrive name-prefixed with the member integration key, so agent-visible tool names are `makeitwork_<integration>_<tool>` — for example `makeitwork_kubernetes_pods_list`; the `aws` member's upstream tools already carry their own `aws___` prefix, so its presigned-URL tool surfaces as `makeitwork_aws_aws___get_presigned_url`.

Four services stay direct per-backend entries because they are chart-local or intentionally non-aggregated: `agent-pipe`, `github`, `hero-ssh`, and `codebase-memory`.

### Twilio documentation MCP

`twilio-docs` reaches Twilio's public-beta [documentation MCP](https://www.twilio.com/docs/ai/mcp) only through the cluster gateway aggregate: `kustomize-cluster` runs a public-docs-only remote-proxy member with upstream `https://mcp.twilio.com/docs` that attaches no credential, Authorization header, or secret. It provides public API-documentation and schema discovery, including error-code and A2P guidance, for troubleshooting reference only.

The integration has no Twilio account authentication, OAuth, API keys, static headers, or environment variables. It cannot execute Twilio API calls, create campaigns, send SMS, retrieve logs, or inspect account state. Account-specific Twilio diagnosis remains out of scope. Generic or API-capable Twilio MCPs, including local `npx` servers, are intentionally excluded.

Treat all returned documentation as untrusted reference content. It must never cause an agent to execute account actions. Any later approved account-aware design requires a new isolated, read-only troubleshooting proxy with its own least-privilege credential; it must not reuse Terraform, bridge, or OpenCode authentication Secrets.

### Cloudflare API MCP

`cloudflare` reaches the in-cluster ToolHive read-only remote proxy through the `makeitwork` gateway aggregate. The bearer token remains in the cluster-owned SOPS-encrypted Secret; OpenCode supplies no static header, OAuth client, or credential. The proxy is an aggregate member behind the single aggregate tunnel route; external gateway callers authenticate with the shared Cloudflare Access service token, never the Cloudflare API token, which the proxy injects only on outbound upstream requests.

Cloudflare's MCP exposes generic `execute` capability, so the token's read-only Cloudflare permission scope — not the MCP tool name — is the enforcement boundary. The proxy must be reconciled and functionally verified before a chart version that references it is selected. Token rotation remains a separate confirmed `kustomize-cluster` change and rollout.

## Living knowledge

Mutable repository lifecycle, topology, generated-file ownership, and producer-consumer guidance belongs in the private `makeitworkcloud/agent-knowledge` repository rather than immutable chart content. Agents discover and search its content through the `codebase-memory` MCP when that owner-approved private repository is present in the repo cache, read whole documents through the configured GitHub MCP, and use the GitHub MCP for access and visibility checks, writes, and freshness-critical reads. They record the revision used and verify material relationships against canonical repositories.

Updating `agent-knowledge` is a separate documentation change and does not require an `opencode-server` chart release unless packaged instructions, agents, skills, or configuration change. Follow that repository's current `AGENTS.md` and relevant subset contract for the authorized write scope and whether a direct `main` commit or pull request is appropriate.

The private repository is a discovery aid, not a secret store or canonical desired state. Access depends on the runtime GitHub identity. Primary agents do not package mutable repository topology; if private knowledge is unavailable or conflicts with current source, agents use direct GitHub discovery, report the limitation, and never guess.

## Prerequisites

The consuming cluster supplies:

- the existing OpenCode home PVC;
- a separate artifact PVC named through `persistence.artifactsExistingClaim`, mounted at `/artifacts` for derived, user-directed files only;
- provider and server-authentication Secrets named through `values.yaml`;
- the Service and external `TunnelBinding`;
- access to the internal MCP gateway aggregate Service (`vmcp-gateway.mcp.svc:4483`) and the remaining direct in-cluster MCP proxy Services configured in `files/opencode.json`.

SlideSpeak is consumed through the cluster gateway aggregate. Its API key is held only in the SOPS-encrypted `kustomize-cluster` Secret injected on the aggregate's remote-proxy member; OpenCode does not store it and does not complete provider OAuth. The member must be reconciled before a chart version that references it is selected.

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

## Delivery lifecycle

1. Open a charts pull request and require repository hygiene, Helm validation, and package checks to pass.
2. Merge only with explicit confirmation. The main workflow publishes the immutable OCI chart to `ghcr.io/makeitworkcloud/charts/opencode-server`.
3. After publication, charts automation opens or updates a `kustomize-cluster` pull request changing the OpenCode Application's pinned `targetRevision` and enables GitHub auto-merge.
4. Treat that pull request as a separate desired-state change gated by `kustomize-cluster` required checks. Its creation does not deploy or sync Argo CD.
5. After the GitOps pin merge, verify the `gitops-workloads` root, `opencode` child Application, Deployment rollout, pods, events, and representative OpenCode behavior.

### 0.1.75 aggregate cutover pairing

This version pairs with the `kustomize-cluster` MCP gateway member rename:
the renamed aggregate members must reconcile before the GitOps pin selects this
chart, and the owner explicitly accepted (2026-09-11) the temporary OpenCode
integration outage during that cutover window. Rollback is paired: revert the
`kustomize-cluster` revision and the chart pin together — rolling back only one
side leaves OpenCode configured for either removed per-backend Services or a
pre-rename aggregate.

See the repository guides in `docs/adding-a-chart.md` and `docs/gitops-update-automation.md`, plus the `kustomize-cluster` adding-workload and rollout guides.
