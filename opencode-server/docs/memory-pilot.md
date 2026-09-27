# Memory pilot

Opt-in isolated rendering of `opencode-server` for the Make IT Work Cloud
memory pilot. Enabling it is a deployment-mode switch, not an additive
feature: one Application renders either production or the pilot, never both.

## Integration contract

| Value | Required pilot setting |
| --- | --- |
| `memoryPilot.enabled` | `true` |
| `fullnameOverride` | exactly `opencode-memory-pilot` |
| `persistence.existingClaim` | exactly `opencode-memory-pilot-home` |
| `memoryPilot.providerSecretName` | exactly `opencode-memory-pilot-provider` (key `ZHIPU_API_KEY`) |
| `memoryPilot.serverSecretName` | exactly `opencode-memory-pilot-server-auth` (key `password`) |
| `memoryPilot.embeddingSecretName` | exactly `opencode-memory-pilot-embeddings` (key `apiToken`) |

Namespace `opencode`. Rendering fails on any other value for these names,
which prevents accidental production collisions — including fullname helper
truncation edge cases and production credential overrides. The pilot never
mounts production secrets (`opencode-zai`, `opencode-kimi`,
`opencode-minimax`, `opencode-openai-auth`, `opencode-server-auth`), the
artifact PVC, packaged production agents, skills, MCP configuration, or any
`auth.json` seed.

The embedding Secret's `apiToken` is injected only at runtime as
`OPENCODE_EMBEDDING_API_KEY`. The owner creates and encrypts this Secret in
`makeitworkcloud/kustomize-cluster` under the existing SOPS `apiToken` match.
Never place plaintext secret contents in chart configuration, values, or Git;
configuration contains only `env://OPENCODE_EMBEDDING_API_KEY`. No global OpenAI
key environment variable is needed. The embedding key does not replace the
isolated Z.AI provider credential or production OpenAI OAuth.

## What renders

- one ConfigMap `opencode-memory-pilot-config` containing exactly
  `opencode.json`, `opencode-mem.jsonc`, and a minimal `AGENTS.md`, seeded
  into `/home/opencode/.config/opencode` through the same init-container
  `emptyDir` copy as production, with no `auth.json` seeding;
- one Deployment `opencode-memory-pilot` with `replicas: 1` and
  `strategy: Recreate`.

OpenCode still serves port 4096 behind a cluster-owned Service in
`kustomize-cluster`, exactly like production. Cross-repo comparison of that
Service against this Deployment is deferred to activation and performed
against the published chart; pull-request checks do not fetch other
repositories.

## Secret rotation

The pilot Deployment opts into Reloader for all three pilot Secrets:
`secret.reloader.stakater.com/reload` lists
`opencode-memory-pilot-provider,opencode-memory-pilot-server-auth,opencode-memory-pilot-embeddings`.
Rotate the provider key, server password, or embedding key only through a
separately confirmed `kustomize-cluster` change. Reloader restarts the pod;
with a single `Recreate` replica that restart is a deliberate full stop, so
rotate while no synthetic run is in flight. A restart may perform billable
remote embedding warmup and requires an approved paid-test scope.

## Runtime shape

- OpenCode `1.18.29` (digest-pinned) starts through `/bin/sh -ec`. The startup
  guard rejects a missing or empty `OPENCODE_EMBEDDING_API_KEY`, or a key
  containing any whitespace, with a fixed diagnostic message; it never logs
  the key. On success it runs
  `exec opencode web --hostname 0.0.0.0 --port 4096`, preserving the server
  arguments. This prevents local fallback caused by empty configuration,
  not invalid credentials, API failures, or insufficient account entitlement;
  passing the guard is not proof the API key is valid. A Kubernetes
  `startupProbe` on port 4096 (period 10 seconds, failure threshold 120) gives
  slow first boots a twenty-minute budget before readiness and liveness
  probing begin. The tcp probe covers server startup only: it verifies the
  listener and does not establish plugin load or embedding-model readiness.
- Chart 0.4.6 configures remote OpenAI embeddings with
  `embeddingApiUrl: "https://api.openai.com/v1"`,
  `embeddingModel: "text-embedding-3-small"`, `embeddingDimensions: 1536`,
  `embeddingUseTaskPrefixes: false`, and
  `embeddingApiKey: "env://OPENCODE_EMBEDDING_API_KEY"`. The manual
  `memoryProvider`/`memoryApiUrl` block remains omitted; there is no fallback
  memory-model API or extraction-provider switch. Z.AI remains the provider
  for conversation and extraction inference.
- Historical local ONNX memory writes failed on the stock Alpine-based image.
  The reviewed pinned plugin source routes remote embeddings around local
  model loading, but real HTTP memory write/search on the exact image remains
  UNTESTED. Source-path review and the startup guard do not prove end-to-end
  runtime success. No custom image or sidecar is introduced.
- The plugin's npm dependencies, including its local
  `@huggingface/transformers` stack, still ship and install. Remote routing
  bypasses local model loading; it does not remove those packages or establish
  any network-blocking guarantee. npm installation and remote embedding
  requests still require egress.
- Startup may issue billable remote warmup requests before an explicit memory
  operation. Starting the pilot and testing real HTTP write/search require
  separately approved paid-test scope, including synthetic payloads and
  accepted usage cost; neither publication nor passing static checks grants
  that approval.
- The `opencode-mem@2.26.0` plugin installs from npm on first boot into the
  persistent home. Plugin settings are the seeded `opencode-mem.jsonc`:
  storage under `/home/opencode/.opencode-mem/data`, automatic capture
  initially off (`autoCaptureEnabled: false`), cleanup off, chat-message
  injection pinned to `injectOn: "first"` with `maxMemories: 3` and
  `excludeCurrentSession: true`, and compaction pinned to `memoryLimit: 10`.
  User-profile learning is effectively off because that path is owned by the
  disabled web server (`webServerEnabled: false`), not because of
  `injectProfile`; `injectProfile: false` additionally prevents any stored
  profile from being injected, and `userProfileAutoCleanupEnabled: false`
  keeps cleanup from touching it.
- The only enabled conversation provider is `zai-coding-plan/glm-5.3` through
  `{env:ZHIPU_API_KEY}`. A valid isolated provider credential remains a
  prerequisite for conversation and extraction; the new embedding key is not
  a substitute. The schema-supported built-in agents build, plan, general,
  and explore are disabled; no other built-in names are guessed. The default
  agent is the synthetic-only `memory-pilot` primary.
- Tooling is constrained by permission rules, not the deprecated `tools`
  field: the global permission denies every tool (`"*": "deny"`) except
  `memory` and the plugin's `StructuredOutput` path, which constrains any
  enabled agent, and the `memory-pilot` agent repeats a deny-all-except-
  memory permission itself. The plugin's internal structured-output agent
  supplies its own permission behavior.

## Synthetic data only

`autoCaptureEnabled: false` does not disable the existing enabled
`chatMessage` path: it still persists raw SYNTHETIC prompts. Every conversation
reaching this instance must be treated as synthetic pilot data, including
payloads that may be sent to the remote embedding API. The synthetic-only rule
is documented operating policy, not an enforced sandbox: the `memory` tool can
import and export files, so treat every path and payload as synthetic pilot
data.

## Persistence

- The pilot is single-replica `Recreate` on a dedicated home claim: no high
  availability and no node-loss protection. `Recreate` reduces the chance of
  two writers overlapping the store; it is not proof of database safety.
- Storage acceptance for this pilot is the persistent home PVC as-is: the
  plugin stores memory data under `/home/opencode/.opencode-mem/data`.
  Historical local-model cache and 768-dimensional vector state may remain
  on a previously used claim.
- Do not silently reuse or reset old 768-dimensional vector state with the new
  1536-dimensional model. Inspect the existing store's embedding metadata
  before activation and obtain separate approval for migration or an empty
  store. There is no automatic deletion or implicit reset authorization.
- OpenCode's own session database is also on the home PVC, separate from the
  plugin store. Never read or upload credentials, including `.auth-token`
  or `auth.json`.
- Never delete lock files automatically; a stale lock is an operator
  decision.

Backup/restore automation and hardening remain deferred, with no node-loss
recovery guarantee. Any manual operator copy is scoped to plugin memory
inventory, database shards, and raw prompt records: classify content first,
exclude `.auth-token`, `auth.json`, and all other credentials unconditionally,
and never export the whole home. OpenCode's session database shares the home
PVC but is outside the plugin backup scope.

## Baseline and checksum parity

The pilot tests retain the historical 0.4.0 baseline commit `32a6b91` and
allow only enumerated agent changes: the QA reviewer's existing end-of-file
correction plus exactly seventeen approved model-header changes, eight
approved session knowledge-read paragraph insertions, and the approved Kimi
provider-id migration of four further frontmatter model-prefix updates and
three exact `files/opencode.json` config-line substitutions. The baseline
`files/agents/qa-engineer.md` lacks a final newline; the render comparison
appends exactly one. The nine primary files (`career.md`, `default.md`,
`grillmaster.md`, `homerepair.md`, `homesteader.md`, `lawnmowerman.md`,
`makeitwork.md`, `teacher.md`, and `xnoto.md`) receive the exact frontmatter
replacement from `openai/gpt-5.6-terra` plus `variant: default` to
`openai/gpt-6-astra` with no variant override. Eight of those primary files
(all except `default.md`) additionally receive the exact session
knowledge-read policy paragraph inserted before one asserted per-file anchor
heading. The six Terra-tier files
(`adversarial-code-reviewer.md`, `cloud-architecture-reviewer.md`,
`devops-engineer.md`, `infra-security-reviewer.md`,
`recruiter-resume-reviewer.md`, and `terra.md`) receive the exact model-line
replacement from `openai/gpt-5.6-terra` to `openai/gpt-6-sol` with each
existing variant preserved. The two Luna-tier files (`luna.md` and
`qa-engineer.md`) receive the exact model-line replacement from
`openai/gpt-5.6-luna` to `openai/gpt-6-luna`. The four Kimi subagents
(`kimi.md` to `kimi-code-plan-cn/k3`; `kimi-256k.md`, `docs-writer.md`, and
`release-engineer.md` to `kimi-code-plan-cn/k3-256k`, each existing variant
preserved) receive the exact model-prefix line replacement from
`kimi-for-coding` to `kimi-code-plan-cn`, and the baseline
`files/opencode.json` receives exactly three config-line substitutions: the
global fallback model, the enabled-provider allowlist entry, and the provider
key. The test asserts each old block
exists exactly once in the extracted baseline header before replacing it,
that each knowledge-read anchor occurs exactly once before inserting, and
that each of the three Kimi config lines occurs exactly once before
substituting; all other agent bytes and production render comparisons remain
enforced.
These changes affect the production ConfigMap checksum relative to the
published 0.4.0 chart, so a normal production pod rollout on the chart version
pin can occur even when the pilot is disabled. No claim is made that the
current production manifest or checksum exactly matches the original baseline.

## Publication and activation

The chart 0.4.6 remote-embedding change leaves production rendering unchanged
from 0.4.5; the historical 0.4.0 parity contract above remains unchanged.
Versioned publication may cause an automatic PRODUCTION chart-pin pull
request in `kustomize-cluster` with auto-merge enabled. Do not confuse that
production delivery path with pilot activation.

Pilot version selection, Application registration, and manual sync are
independent actions, each requiring separate confirmation of its exact target
and operation. Before activation, resolve existing-store metadata and any
separately approved migration or empty-store decision, ensure all three isolated
provider, server-auth, and embedding credentials are supplied, and approve the paid-test
scope even for startup warmup. Exact-image HTTP memory write/search remains
a required runtime validation, not an outcome established by these docs or
static chart checks.

## Security posture

Non-root UID/GID/fsGroup 1000, read-only root filesystems, all capabilities
dropped, no Service Account token automount, no Service resources rendered,
no resource requests or limits (single-node repo policy), and no production
credential grants.
