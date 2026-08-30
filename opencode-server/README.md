# OpenCode server chart

Helm chart for the shared Make IT Work Cloud OpenCode web server and its non-secret global configuration.

## Ownership

This chart owns the OpenCode Deployment and chart-packaged non-secret configuration. `makeitworkcloud/kustomize-cluster` owns the consuming Argo CD Application, namespace integration, persistent storage, Services, TunnelBinding, and SOPS-encrypted Secrets.

Every Kubernetes object has one owner. Do not duplicate cluster-owned resources in this chart.

## Packaged configuration

The chart copies these immutable package inputs into `/home/opencode/.config/opencode` at pod startup:

- `files/opencode.json` — providers, enabled MCP integrations, default agent, and global OpenCode configuration
- `files/AGENTS.md` — shared instructions loaded by every agent
- `files/agents/*.md` — owner-specific primary agents
- `files/skills/*/SKILL.md` — specialized operational workflows

A change to any packaged file is chart content and requires a new `Chart.yaml` version.

## Prerequisites

The consuming cluster supplies:

- the existing OpenCode home PVC;
- provider and server-authentication Secrets named through `values.yaml`;
- the Service and external `TunnelBinding`;
- access to the in-cluster MCP proxy Services configured in `files/opencode.json`.

Never put credentials, decrypted values, kubeconfigs, private keys, or tokens in chart files or values.

## Rendered resources

- Deployment with an init container that seeds immutable chart configuration into an `emptyDir`
- ConfigMap containing OpenCode configuration, agents, and skills

Configuration is loaded when OpenCode starts. A reconciled chart update replaces the pod through the ConfigMap checksum annotation; it is not hot-reloaded into an existing process.

## Delivery lifecycle

1. Open a charts pull request and require repository hygiene, Helm validation, and package checks to pass.
2. Merge only with explicit confirmation. The main workflow publishes the immutable OCI chart to `ghcr.io/makeitworkcloud/charts/opencode-server`.
3. After publication, charts automation opens or updates a `kustomize-cluster` pull request changing the OpenCode Application's pinned `targetRevision`.
4. Review that pull request independently. Its creation does not deploy or sync Argo CD.
5. After an explicitly confirmed GitOps merge, verify the `gitops-workloads` root, `opencode` child Application, Deployment rollout, pods, events, and representative OpenCode behavior.

See the repository guides in `docs/adding-a-chart.md` and `docs/gitops-update-automation.md`, plus the `kustomize-cluster` adding-workload and rollout guides.
