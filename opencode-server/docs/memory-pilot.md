# Memory pilot

Opt-in isolated rendering of `opencode-server` for the Make IT Work Cloud
memory pilot. Enabling it is a deployment-mode switch, not an additive
feature: one Application renders either production or the pilot, never both.

## Integration contract

| Value | Required pilot setting |
| --- | --- |
| `memoryPilot.enabled` | `true` |
| `fullnameOverride` | `opencode-memory-pilot` |
| `persistence.existingClaim` | `opencode-memory-pilot-home` |
| `memoryPilot.providerSecretName` | `opencode-memory-pilot-provider` (key `ZHIPU_API_KEY`) |
| `memoryPilot.serverSecretName` | `opencode-memory-pilot-server-auth` (key `password`) |

Namespace `opencode`. Rendering fails when `memoryPilot.enabled=true` is
combined with the production fullname `opencode`, the production home claim
`opencode-home`, or empty values for either. The pilot never mounts production
secrets (`opencode-zai`, `opencode-kimi`, `opencode-minimax`,
`opencode-openai-auth`, `opencode-server-auth`), the artifact PVC, packaged
production agents, skills, MCP configuration, or any `auth.json` seed.

## What renders

- one ConfigMap `opencode-memory-pilot-config` containing exactly
  `opencode.json`, `opencode-mem.jsonc`, and a minimal `AGENTS.md`, seeded
  into `/home/opencode/.config/opencode` through the same init-container
  `emptyDir` copy as production, with no `auth.json` seeding;
- one Deployment `opencode-memory-pilot` with `replicas: 1` and
  `strategy: Recreate`.

## Runtime shape

- OpenCode `1.18.29` (digest-pinned) waits for the embedding sidecar's
  `127.0.0.1:8080/health` endpoint using a busybox `wget` loop with a
  ten-minute deadline before `exec`-ing `opencode web` on port 4096, because
  the memory plugin caches embedding warm-up failures.
- Embeddings come only from the same-pod
  `ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4` sidecar running
  `nomic-ai/nomic-embed-text-v1` at revision
  `3ac47f125a41961d13b397d0332866be2f9152e1` (768 dimensions, Nomic task
  prefixes, auto-truncate). It binds `127.0.0.1:8080` only and has no
  Service. There is no external embedding or fallback API: `embeddingApiKey`
  is the non-secret `-` placeholder for the no-auth loopback endpoint.
- The sidecar model cache is an `emptyDir`: every pod start re-downloads the
  model into `/models`, so first starts can take minutes. Its startup probe
  allows ten minutes for that download.
- The `opencode-mem@2.26.0` plugin installs from npm on first boot into the
  persistent home. Plugin settings are the seeded `opencode-mem.jsonc`:
  storage under `/home/opencode/.opencode-mem/data`, capture on, cleanup and
  web server off, profile learning off (`injectProfile: false`,
  `userProfileAutoCleanupEnabled: false`).
- The only enabled provider is `zai-coding-plan/glm-5.3` through
  `{env:ZHIPU_API_KEY}`; built-in agents build, plan, general, and explore
  are disabled; the default agent is the synthetic-only `memory-pilot`
  primary whose only enabled tool is `memory`. The plugin's internal
  structured-output paths through the OpenCode session API stay usable.

## Synthetic data only

While `chatMessage.enabled` is true the plugin persists raw prompts, and the
pilot has no independent toggle for that. Every conversation reaching this
instance must be treated as synthetic pilot data.

## Persistence, backups, and restore

- The pilot is single-replica `Recreate` on a node-local home claim: no high
  availability, and a pod restart is a deliberate full stop.
- Back up the full `.opencode-mem` directory, including `.auth-token` if the
  plugin created one; do not back up the whole home directory and never
  `auth.json`.
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
dropped, no Service Account token automount, no Service exposure, no
resource requests or limits (single-node repo policy), and no production
credential grants.
