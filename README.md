# charts

Helm chart monorepo for Make IT Work Cloud workloads. Each direct child
directory containing `Chart.yaml` is a chart consumed by ArgoCD from this Git
repository.

## Charts

| Chart | Purpose |
| --- | --- |
| `opencode-server/` | OpenCode server Deployment and its non-secret configuration ConfigMap |

## Validation

Pull requests run repository hygiene plus `helm lint --strict` and
`helm template` for every chart. Merges to `main` make the updated source
available to ArgoCD; they do not publish an OCI chart.

## Adding a chart

1. Add `<chart>/Chart.yaml` and templates.
2. Include chart-local configuration files under `<chart>/files/` when they are
   rendered through Helm's `.Files` object.
3. Update this README and open a PR.
