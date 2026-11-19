# Agent Instructions

## Repository Purpose

Helm chart monorepo for Make IT Work Cloud workloads. Every direct child directory
containing `Chart.yaml` is an independently validated chart. Merges to `main`
publish changed charts as OCI artifacts to GHCR.

OpenCode runtime policy is owned by the [opencode-server chart](opencode-server/docs/agent-instruction-architecture.md), not by this repository guide.

Use repository CI as the validation authority for chart changes.

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
  `agents/*.md`, `skills/*/SKILL.md` — requires an
  `opencode-server/Chart.yaml` version bump because OCI chart versions are
  immutable.
- After `opencode-server` publishes, automation opens or updates a
  `kustomize-cluster` version-pin pull request with auto-merge enabled; see
  [GitOps update automation](docs/gitops-update-automation.md) for the current
  contract. Argo CD reconciliation and rollout health are verified separately
  afterward.
