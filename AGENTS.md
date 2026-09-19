# Agent Instructions

## Repository Purpose

Helm chart monorepo for Make IT Work Cloud workloads. Every direct child directory
containing `Chart.yaml` is an independently validated chart. Merges to `main`
publish changed charts as OCI artifacts to GHCR.

## Session boundary and available MCPs

- OpenCode is an in-cluster MCP client. It connects directly to the configured
  ClusterIP Services: `agent-pipe`; the 14 ToolHive backend proxies `apify`,
  `argocd`, `aws`, `aws-docs`, `cloudflare`, `context7`, `gcp`, `grafana`,
  `kubernetes`, `parallel-search`, `playwright`, `slidespeak`,
  `terraform-docs`, and `twilio-docs`; and the direct `codebase-memory`,
  `github`, and `hero-ssh` proxies. Direct tool names do not use a
  `makeitwork_` aggregate prefix.
- `vmcp-gateway` is reserved for external consumers only. Do not configure it
  as an OpenCode MCP client or expose duplicate aggregate and direct entries.
- For Make IT Work Cloud repository exploration, use the direct
  `codebase-memory` MCP over its read-only cache at `/repos/<repo>/current`.
  This path belongs to the remote backend, not OpenCode's local filesystem.
  Check `list_projects` and `index_status` for the actual indexed root,
  snapshot revision, and coverage; project names alone do not prove freshness.
  Re-index missing or stale projects with explicit `mode: "full"` when
  documentation is needed; fast mode excludes documentation directories.
  Discover a document's `Module` using `search_graph` and pass the returned
  exact qualified name to `get_code_snippet`. Accept a complete-document read
  only when the indexed range starts at line 1, covers the required document,
  and matches the returned extent without clipping or reported partial coverage.
  In the deployed 0.10.8 interface, snippets cap at 500 lines and File nodes
  without ranges fall back to 51 lines; there is no paging argument. Use GitHub
  MCP for missing, excluded, partial, incomplete, or clipped content, at the
  same snapshot revision when possible. Index coverage is best-effort, not
  proof of parser completeness. Do not use GitHub file reads as an alternate
  broad discovery path.
- Use the direct `github` MCP integration exclusively for GitHub-specific
  operations: writes, branches, pull requests, reviews, workflow evidence,
  private-repository access and visibility checks, and freshness-critical reads.
  Verify remote default-branch HEAD before branching or publishing. Cached
  private content is limited to owner-approved repositories and does not prove
  current authorization. Do not assume a local checkout or use `git`, `gh`,
  SSH, or workstation paths.
- Use the direct `argocd` and `kubernetes` tools immediately for read-only
  cluster and application diagnostics. Do not sync, patch, delete, or run
  resource actions without explicit user approval.
- Use the direct `context7`, `terraform-docs`, `aws-docs`, and `grafana` tools,
  and web research as applicable for current library, provider, cloud,
  observability, and runtime behavior. Do not guess schemas, provider behavior,
  CI behavior, or cluster state.
- CI is authoritative. Do not claim local Helm, OpenTofu, pre-commit, or other
  validation ran from the shared server.

## Workflow

Use feature branches and pull requests. Agents may create a scoped branch,
commit, push, and open a pull request for an authorized repository change
without requesting a separate confirmation. Inspect protected-branch metadata,
PR templates, reviews, and check runs, and never bypass protections. Explicit
user approval remains required before merging, publishing a package,
dispatching a workflow, deploying, or mutating a live system.

Before publishing, inspect proposed changed files for secrets, state,
kubeconfig material, decrypted SOPS values, tokens, credentials, private keys,
and sensitive plan output.

## Chart conventions

- Use [Adding a chart](docs/adding-a-chart.md) for the authoring and release
  procedure. Use [GitOps update automation](docs/gitops-update-automation.md)
  for the optional post-publish pull request contract.
- Keep each chart self-contained below its chart directory.
- Do not place plaintext credentials, kubeconfigs, tokens, or decrypted SOPS
  values in charts or values files.
- Cluster-owned secrets, namespaces, storage, and shared networking remain in
  `kustomize-cluster` unless a migration explicitly moves their ownership.
- Add `<chart>/README.md` for chart-specific ownership, values, prerequisites,
  and usage; update it when that contract changes. CI discovers direct-child
  charts automatically.
- Every `opencode-server/files/` content change — configuration, `AGENTS.md`,
  `agents/*.md`, `skills/*/SKILL.md` — requires an `opencode-server/Chart.yaml`
  version bump because OCI chart versions are immutable.
- After `opencode-server` publishes, automation opens or updates a
  `kustomize-cluster` version-pin pull request with auto-merge enabled; see
  [GitOps update automation](docs/gitops-update-automation.md) for the current
  contract. Argo CD reconciliation and rollout health are verified separately
  afterward.
