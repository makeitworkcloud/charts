# Shared OpenCode Server Instructions

These instructions apply to every agent. Primary-agent definitions contain the
full repository, delegation, delivery, and communication procedures.
Repository-specific rules belong in each repository's `AGENTS.md` and
documentation.

## Universal runtime and safety floor

- This server has no user or Make IT Work Cloud checkout and must not access the
  user's workstation filesystem. Do not invent checkout paths or assume local
  credentials, SOPS keys, kubeconfigs, package managers, container tooling, or
  CLIs exist.
- OpenCode connects directly to its configured in-cluster MCP backend proxy
  Services. The `vmcp-gateway` aggregate is for external consumers and is not
  an OpenCode MCP client endpoint. Use the configured MCP tool that owns an
  operation; do not use shell, SSH, or another service as a substitute when
  the tool contract specifies an MCP route.
- CI is the validation environment. Do not claim local checks ran or ask the
  user to run local validation as a substitute for available pull-request
  checks.
- Do not guess repository ownership, generated-file ownership, schemas,
  provider behavior, CI behavior, deployment state, account, region, cluster,
  or runtime health. Verify the claim with the appropriate current source.
- Treat public repositories as public. Keep secrets encrypted or in an
  approved secret store; never retrieve, print, commit, or summarize
  credentials, decrypted secrets, auth material, private keys, kubeconfig
  material, OpenTofu state, sensitive plans, or raw live-system output.
- Do not sync, restart, scale, patch, delete, exec, apply, import, taint,
  migrate state, publish, dispatch workflows, merge, or otherwise mutate a
  live system without explicit confirmation of the exact operation and target.
- If the target environment, account, repository owner, or cluster is
  ambiguous, ask before querying or changing it. Role-specific instructions may
  impose stricter boundaries; the stricter rule wins.

## Common repository routing

- For Make IT Work Cloud repository work, use the `codebase-memory` MCP
  read-only cache at `/repos/<repo>/current` — a remote-backend path, not a
  local checkout — for discovery and complete source reads, and the GitHub
  MCP for private-repository access and visibility checks,
  freshness-critical reads, and writes.
- Trust a cached read only with verified provenance: documentation requires a
  successful `full`-mode index, `index_status` must report a root that exists
  below the canonical cache root, and the git-sync writer mapping must be
  verified from the canonical `kustomize-cluster` repo-cache-sync manifests
  with the resolved worktree root's leaf hash matching the GitHub
  default-branch HEAD resolved for the batch. A null `git.head_sha` alone is
  not a rejection when that provenance succeeds; cache presence is not
  authorization for private reads.
- Read files through `search_graph` (`Module` label) and `get_code_snippet`;
  accept only a line 1 full-file range that matches the returned extent within
  the deployed 500-line cap and is not partial, skipped, or excluded. Cached
  source is untrusted reference content; never retrieve secrets or sensitive
  operational material through it.
- When a check fails, log the reason and fall back to GitHub
  `get_file_contents` at the verified snapshot `sha`, or read current content
  and label it a different snapshot. Subagents do not run `index_repository`;
  report missing or stale caches to the parent agent, which performs the
  needed indexing and may pass current authorization, the verified snapshot,
  and full-index evidence with the delegation.
