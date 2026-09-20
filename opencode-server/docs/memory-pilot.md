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

Namespace `opencode`. Rendering fails on any other value for these names,
which prevents accidental production collisions — including fullname helper
truncation edge cases and production credential overrides. The pilot never
mounts production secrets (`opencode-zai`, `opencode-kimi`,
`opencode-minimax`, `opencode-openai-auth`, `opencode-server-auth`), the
artifact PVC, packaged production agents, skills, MCP configuration, or any
`auth.json` seed.

## What renders

- one ConfigMap `opencode-memory-pilot-config` containing exactly
  `opencode.json`, `opencode-mem.jsonc`, and a minimal `AGENTS.md`, seeded
  into `/home/opencode/.config/opencode` through the same init-container
  `emptyDir` copy as production, with no `auth.json` seeding;
- one Deployment `opencode-memory-pilot` with `replicas: 1` and
  `strategy: Recreate`.

OpenCode still serves port 4096 behind a cluster-owned Service in
`kustomize-cluster`, exactly like production.

## Runtime shape

- OpenCode `1.18.29` (digest-pinned) starts directly with
  `opencode web --hostname 0.0.0.0 --port 4096`. A Kubernetes `startupProbe`
  on port 4096 (period 10 seconds, failure threshold 120) gives slow first
  boots a twenty-minute budget before readiness and liveness probing begin.
  The tcp probe covers server startup only: it verifies the listener and
  does not establish plugin load or embedding-model readiness.
- Embeddings use the plugin's local ONNX default,
  `Xenova/nomic-embed-text-v1`, with `embeddingDimensions: 768` and
  `embeddingUseTaskPrefixes: true`. No remote embedding endpoint is
  configured: `embeddingApiUrl` and `embeddingApiKey` are omitted, and the
  manual `memoryProvider`/`memoryApiUrl` block only activates when
  explicitly configured and is omitted, so no external embedding or model
  endpoint exists beyond the `{env:ZHIPU_API_KEY}` provider.
- Removing the former embedding sidecar does not remove Hugging Face
  dependencies: the plugin still ships its local `@huggingface/transformers`
  stack and downloads the ONNX model from Hugging Face on first use.
- Local ONNX embedding compatibility on the stock Alpine-based OpenCode
  image is UNVERIFIED. It is an activation gate: verify package
  compatibility and native runtime behavior before registering or syncing
  the pilot. Persistent home storage does not solve it — the model cache
  persists under the storage path, but compatibility must be proven at
  runtime.
- The `opencode-mem@2.26.0` plugin installs from npm on first boot into the
  persistent home. Plugin settings are the seeded `opencode-mem.jsonc`:
  storage under `/home/opencode/.opencode-mem/data`, capture on, cleanup
  off, chat-message injection pinned to `injectOn: "first"` with
  `maxMemories: 3` and `excludeCurrentSession: true`, and compaction pinned
  to `memoryLimit: 10`. User-profile learning is effectively off because
  that path is owned by the disabled web server (`webServerEnabled: false`),
  not because of `injectProfile`; `injectProfile: false` additionally
  prevents any stored profile from being injected, and
  `userProfileAutoCleanupEnabled: false` keeps cleanup from touching it.
- The only enabled provider is `zai-coding-plan/glm-5.3` through
  `{env:ZHIPU_API_KEY}`. The schema-supported built-in agents build, plan,
  general, and explore are disabled; no other built-in names are guessed.
  The default agent is the synthetic-only `memory-pilot` primary.
- Tooling is constrained by permission rules, not the deprecated `tools`
  field: the global permission denies every tool (`"*": "deny"`) except
  `memory` and the plugin's `StructuredOutput` path, which constrains any
  enabled agent, and the `memory-pilot` agent repeats a deny-all-except-
  memory permission itself. The plugin's internal structured-output agent
  supplies its own permission behavior.

## Synthetic data only

While `chatMessage.enabled` is true the plugin persists raw prompts, and the
pilot has no independent toggle for that. Every conversation reaching this
instance must be treated as synthetic pilot data. The synthetic-only rule is
documented operating policy, not an enforced sandbox: the `memory` tool can
import and export files, so treat every path and payload as synthetic pilot
data.

## Persistence

- The pilot is single-replica `Recreate` on a dedicated home claim: no high
  availability and no node-loss protection. `Recreate` reduces the chance of
  two writers overlapping the store; it is not proof of database safety.
- Storage acceptance for this pilot is the persistent home PVC as-is: the
  plugin stores memory data and the local embedding cache under
  `/home/opencode/.opencode-mem/data`.
- Backup and restore automation is deferred; no backup design is specified
  here. If an operator takes a manual copy, scope it to the plugin memory
  inventory (database, shards, raw-prompt records), classify the content
  first, and exclude credentials — `.auth-token` is treated as a credential
  and is never included — and never copy the whole home directory or
  `auth.json`. No agent may read or upload credentials.
- OpenCode's own session database is also on the home PVC; it is outside
  the plugin backup scope, not outside the claim.
- Never delete lock files automatically; a stale lock is an operator
  decision.

## Security posture

Non-root UID/GID/fsGroup 1000, read-only root filesystems, all capabilities
dropped, no Service Account token automount, no Service resources rendered,
no resource requests or limits (single-node repo policy), and no production
credential grants.
