---
name: opencode-chart-release-and-gitops-rollout
description: Use when changing charts/opencode-server, OpenCode agents, OpenCode skills, or server configuration and planning the separate GitOps rollout.
---

# OpenCode chart delivery

`charts/opencode-server` owns the packaged server configuration. Any content change requires a `Chart.yaml` version bump because OCI chart versions are immutable.

1. Update the chart and every affected rendered ConfigMap or volume input together.
2. Open a charts pull request and use its repository-hygiene, Helm-rendering, and packaging checks as validation evidence.
3. A confirmed merge publishes the chart to GHCR. The successful main workflow then opens or updates a `kustomize-cluster` pull request that pins the OpenCode Application to the new version.
4. Treat the generated GitOps pull request as a separate desired-state change. The confirmed charts merge authorizes publication and enables the downstream auto-merge pin PR; `kustomize-cluster` required checks gate that merge. Creating the pin PR does not sync Argo CD or deploy.
5. After the GitOps pin merge, verify root and child Application revisions, sync and health, resource rollout, and representative OpenCode behavior separately. Do not infer those stages from publication or PR creation.

If independent confirmation for the GitOps pin merge is required, disable auto-merge and update the chart docs consistently.

Do not merge, deploy, sync Argo CD, or modify the running service without explicit confirmation.
