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
`kustomize-cluster`, exactly like production. Only the embedding sidecar is
never exposed by a Service.

## Runtime shape

- OpenCode `1.18.29` (digest-pinned) waits for the embedding sidecar's
  `127.0.0.1:8080/health` endpoint using a busybox `wget -T 2` loop with a
  date-based ten-minute deadline before `exec`-ing `opencode web` on port
  4096, because the memory plugin caches embedding warm-up failures. A
  Kubernetes `startupProbe` on port 4096 (period 10 seconds, failure
  threshold 120) provides a twenty-minute budget that covers the wait plus
  the first-boot npm plugin install; readiness and liveness probing only
  begin after startup succeeds, so the tcp liveness probe cannot kill the
  still-waiting container.
- Embeddings come only from the same-pod
  `ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4` sidecar running
  `nomic-ai/nomic-embed-text-v1` at revision
  `3ac47f125a41961d13b397d0332866be2f9152e1` (768 dimensions, Nomic task
  prefixes, auto-truncate). The sidecar image, model, and revision are fixed
  in the chart templates, not configurable values. The sidecar binds
  `127.0.0.1:8080` only and is never exposed by a Service.
- Both remote embedding fields are set, which is how the plugin skips its
  local ONNX backend; `embeddingApiKey` is the non-secret `-` placeholder for
  the no-auth loopback endpoint. The manual `memoryProvider`/
  `memoryApiUrl` memory-API block only activates when explicitly configured
  and is omitted, so no external embedding or model endpoint exists beyond
  the loopback TEI and the `{env:ZHIPU_API_KEY}` provider.
- The sidecar model cache is an `emptyDir`: every pod start re-downloads the
  model into `/models`, so first starts can take minutes. Its startup probe
  allows ten minutes for that download.
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

## Persistence, backups, and restore

- The pilot is single-replica on a node-local home claim: no high
  availability. `Recreate` reduces the chance of two writers overlapping the
  store; it is not proof of database safety.
- Backup scope is the plugin memory inventory only: its database, shards,
  and raw-prompt records under `.opencode-mem`. An operator must classify
  that content and confirm it excludes credentials before any copy is
  taken; `.auth-token` is treated as a credential and is never included.
  Do not back up the whole home directory and never `auth.json`. No agent
  may read or upload credentials at any point in a backup or restore.
- OpenCode's own session database is also on the home PVC; it is outside
  the plugin backup scope, not outside the claim.
- There is no automated backup until a destination and encryption approach
  are selected. Backup is a cold, manual operation: stop the pod before
  copying so the store is consistent.
- Never delete lock files automatically; a stale lock is an operator
  decision.
- Restart and restore tests are external gates. A successful render and
  rollout says nothing about restore correctness, and no production use may
  depend on this store until those gates pass.

## Security posture

Non-root UID/GID/fsGroup 1000, read-only root filesystems, all capabilities
dropped, no Service Account token automount, no Service exposure for the TEI
sidecar, no resource requests or limits (single-node repo policy), and no
production credential grants.
