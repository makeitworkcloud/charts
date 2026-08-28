---
name: opencode-chart-release-and-gitops-rollout
description: Use when changing charts/opencode-server, OpenCode agents, OpenCode skills, or server configuration and planning the separate GitOps rollout.
---

# OpenCode chart delivery

`charts/opencode-server` owns the packaged server configuration. Any content change requires a Chart.yaml version bump because OCI versions are immutable.

1. Update the chart and its rendered ConfigMap inputs together.
2. Open a PR and use charts CI as validation evidence.
3. A merge publishes the chart to GHCR but does not update the running service.
4. Only after publication, a separate explicitly confirmed `kustomize-cluster` PR may pin the Argo CD Application to that chart version.

Do not deploy, sync Argo CD, or modify the running service without explicit confirmation.
