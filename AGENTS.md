# Agent Instructions

## Repository Purpose

Helm chart monorepo for Make IT Work Cloud workloads. Every direct child directory
containing `Chart.yaml` is an independently validated chart. Merges to `main`
publish changed charts as OCI artifacts to GHCR.

## Session boundary and available MCPs

- Use the configured `github` MCP integration exclusively for repository and
  GitHub operations. Do not assume a local checkout or use `git`, `gh`, SSH, or
  workstation paths.
- Use `argocd` and `kubernetes` MCPs immediately for read-only cluster and
  application diagnostics. Do not sync, patch, delete, or run resource actions
  without explicit user approval.
- Use `context7`, `terraform-docs`, `aws-docs`, Grafana, and web research as
  applicable for current library, provider, cloud, observability, and runtime
  behavior. Do not guess schemas, provider behavior, CI behavior, or cluster
  state.
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
- `opencode-server/files/opencode.json`, `opencode-server/files/AGENTS.md`,
  `opencode-server/files/agents/*.md`, and
  `opencode-server/files/skills/*/SKILL.md` are rendered into the chart
  ConfigMap. Bump `opencode-server/Chart.yaml` for every content change because
  OCI chart versions are immutable.
- After `opencode-server` is published, the current workflow opens or updates a
  `kustomize-cluster` pull request that pins the Argo CD Application to the new
  version. The pull request still requires normal checks, review, and merge; it
  does not sync Argo CD or deploy directly.
