# charts

Helm chart monorepo for Make IT Work Cloud workloads. Each direct child
directory containing `Chart.yaml` is an independently validated and published
chart.

## Charts

| Chart | Purpose |
| --- | --- |
| `opencode-server/` | OpenCode server Deployment and its non-secret configuration ConfigMap |

## Validation and publication

Pull requests run repository hygiene plus `helm lint --strict`, `helm template`,
and package each changed chart without publishing it. A merge to `main` packages
changed charts and publishes them as immutable OCI artifacts to GHCR under:

```text
oci://ghcr.io/makeitworkcloud/charts/<chart-name>
```

ArgoCD should consume a published chart by its explicit chart version. A future
full Helm migration may introduce an approved mechanism for selecting newer
chart versions automatically.

## Adding a chart

1. Add `<chart>/Chart.yaml` and templates.
2. Include chart-local configuration files under `<chart>/files/` when they are
   rendered through Helm's `.Files` object.
3. Bump `version` in `Chart.yaml` for every published chart change; OCI chart
   versions are immutable.
4. Update this README and open a PR.
