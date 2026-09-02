---
name: provider-failover
description: Use when a delegated subagent call fails on provider capacity — rate limit, quota exhaustion, authentication or entitlement failure, or repeated provider-availability errors — and a retry on another provider is being considered.
---

# Provider failover

Apply only after OpenCode's own retry behavior is exhausted, and only for
capacity failures — not for task errors.

Rules (also stated in the shared instructions):

- Never retry with a sibling model of the same provider as the failed call.
- Preserve the original bounded prompt and evidence requirements verbatim.
- At most two cross-provider fallback attempts; never loop a depleted provider,
  broaden the task, or conceal a capability downgrade.
- Record which providers failed and which fallback supplied evidence.
- If no suitable independent provider is available, return the provider
  limitation as a blocker.

Cross-provider fallback chains:

- `glm` or `glm-flash` (Z.AI) -> `kimi-256k` (Kimi) -> `luna` (OpenAI)
- `kimi-256k` or `kimi` (Kimi) -> `glm` (Z.AI) -> `luna` (OpenAI)
- `luna` (OpenAI) -> `kimi-256k` (Kimi) -> `glm` (Z.AI)
- `minimax` (MiniMax) -> `kimi` (Kimi) -> `luna` (OpenAI)

These chains recover delegated calls only. A primary model whose provider
fails before the agent can answer has no automatic failover; an operator must
select a primary agent backed by another provider.
