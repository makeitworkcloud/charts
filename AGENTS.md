# Agent Instructions

## Repository Purpose

Helm chart monorepo for Make IT Work Cloud workloads. Every direct child directory
containing `Chart.yaml` is an independently validated chart. Merges to `main`
publish changed charts as OCI artifacts to GHCR.

## Session boundary and available MCPs

- For public Make IT Work Cloud repository exploration on this shared server, use `repo-search` as the mandatory first read path: inspect `/repos/<repo>/current`, identify and record the adjacent hash-named worktree SHA, then use a bounded `read_multiple_files` request. Do not use GitHub file reads as an alternate discovery path.
- Use the configured `github` MCP integration exclusively for GitHub-specific operations: writes, branches, pull requests, reviews, workflow evidence, private repositories, and freshness-critical reads. Do not assume a local checkout or use `git`, `gh`, SSH, or workstation paths.
- Use `argocd` and `kubernetes` MCPs immediately for read-only cluster and application diagnostics. Do not sync, patch, delete, or run resource actions without explicit user approval.
- Use `context7`, `terraform-docs`, `aws-docs`, Grafana, and web research as applicable for current library, provider, cloud, observability, and runtime behavior. Do not guess schemas, provider behavior, CI behavior, or cluster state.
- CI is authoritative. Do not claim local Helm, OpenTofu, pre-commit, or other validation ran from the shared server.

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
