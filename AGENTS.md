# Agent Instructions

## Repository Purpose

Helm chart monorepo for Make IT Work Cloud workloads. Every direct child directory
containing `Chart.yaml` is an independently validated chart. Merges to `main`
publish changed charts as OCI artifacts to GHCR.

## Session boundary and available MCPs

- MCP integrations on this shared server arrive through one internal gateway
  aggregate entry, `makeitwork` (`http://vmcp-gateway.mcp.svc:4483/mcp`, owned
  by `kustomize-cluster` `workloads/mcp-gateway`). Aggregate tools are exposed
  as `makeitwork_<integration>_<tool>` — for example
  `makeitwork_kubernetes_pods_list`, and
  `makeitwork_aws_aws___get_presigned_url` because the `aws` member's upstream
  tools already carry their own `aws___` prefix. Current members include
  `apify`, `argocd`, `aws`, `aws-docs`, `cloudflare`, `context7`, `gcp`,
  `grafana`, `kubernetes`, `parallel-search`, `playwright`, `slidespeak`,
  `terraform-docs`, and `twilio-docs`.
- Four integrations stay direct per-backend entries because they are
  chart-local or intentionally non-aggregated: `agent-pipe`, `github`,
  `hero-ssh`, and `codebase-memory`.
- For Make IT Work Cloud repository exploration on this shared server, use the
  direct `codebase-memory` MCP as the first discovery path: index and query
  projects at `/repos/<repo>/current`, re-indexing when a project is missing or
  its results appear stale (seconds per repo), and read exact file contents
  through GitHub. Do not use GitHub file reads as an alternate discovery path.
- Use the direct `github` MCP integration exclusively for GitHub-specific
  operations: writes, branches, pull requests, reviews, workflow evidence,
  private repositories, and freshness-critical reads. Do not assume a local
  checkout or use `git`, `gh`, SSH, or workstation paths.
- Use the aggregate's `argocd` and `kubernetes` tools immediately for read-only
  cluster and application diagnostics. Do not sync, patch, delete, or run
  resource actions without explicit user approval.
- Use the aggregate's `context7`, `terraform-docs`, `aws-docs`, and `grafana`
  tools, and web research as applicable for current library, provider, cloud,
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
kubeconfig material, decrypted values, tokens, credentials, private keys, and
sensitive plan output.

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
