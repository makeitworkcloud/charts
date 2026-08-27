# Agent Instructions

## Repository Purpose

Helm chart monorepo for Make IT Work Cloud workloads. Every direct child directory
containing `Chart.yaml` is an independently validated chart. Merges to `main`
publish changed charts as OCI artifacts to GHCR.

## Workflow

Use feature branches and pull requests. CI is authoritative: do not claim local
Helm or pre-commit checks ran from the shared server. Chart versions are immutable:
bump `Chart.yaml` for every chart change that must be published. ArgoCD currently
consumes a chart at an explicit version; do not use mutable OCI tags as a deployment
mechanism.

## Chart conventions

- Keep each chart self-contained below its chart directory.
- Do not place plaintext credentials, kubeconfigs, tokens, or decrypted SOPS
  values in charts or values files.
- Cluster-owned secrets, namespaces, storage, and shared networking remain in
  `kustomize-cluster` unless a migration explicitly moves their ownership.
- Update the chart README and CI coverage when adding a chart.
