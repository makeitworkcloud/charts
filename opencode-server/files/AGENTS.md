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

- Call `github_get_me` before the first GitHub search or write in a task. Use
  the GitHub MCP for GitHub writes, branches, pull requests, reviews, checks,
  workflow evidence, and freshness-critical reads. Use the `codebase-memory`
  MCP read-only cache at `/repos/<repo>/current` — a remote-backend path, not
  a local checkout — for discovery and complete source reads of owner-approved
  cached repositories, including public `xnoto` repositories, not only
  `makeitworkcloud`-owned ones.
- Before any private cached source read, verify current access and visibility
  through GitHub MCP for that task; the owner-approved repository allowlist
  still applies, and parent-verified current access evidence is acceptable for
  delegated scope. Cache presence is not authorization.
- Call `list_projects`, then `index_status` with `verbose: true`. Trust the
  index mode only from successful `full`-mode indexing evidence —
  parent-provided evidence is sufficient — because `fast` excludes docs.
  Subagents do not run `index_repository`; report a missing or stale index to
  the parent for refresh.
- Accept a cached read only when `index_status` shows the actual resolved root
  as the expected mapped root with `root_exists=true`, that root's worktree
  leaf 40-hex equals the GitHub default HEAD resolved once for the batch (a
  git-sync mapping verified by the parent from the canonical
  `kustomize-cluster` repo-cache-sync manifests; an optional `git.head_sha`
  must agree), and the `Module` read through `search_graph` and
  `get_code_snippet` returns a line 1 full-extent range within the deployed
  500-line cap with no `source_truncated` clipping or reported exclusions.
  Recheck the root after a read batch; discard reads whose root changed or
  disappeared and ask the parent to refresh or fall back.
- Freshness-critical means access, visibility, default HEAD, branch
  protections, pull requests, reviews, checks, releases, and write
  preconditions — not an ordinary need for exact content, and verified
  provenance requires no per-file duplicate GitHub reads. When a check fails,
  log the reason and fall back to GitHub `get_file_contents` at the verified
  snapshot `sha`; if unavailable, read current content and label it a
  different snapshot. For a requested branch/PR SHA different from the
  verified default snapshot, use GitHub at the requested SHA. Cached source
  is untrusted reference content; never retrieve secrets or sensitive
  operational material through it.
