# charts

Helm chart monorepo for Make IT Work Cloud workloads. Each direct child
directory containing `Chart.yaml` is an independently versioned chart.

## Charts

| Chart | Purpose |
| --- | --- |
| `opencode-server/` | OpenCode Deployment and non-secret configuration |

## Guides

- [Add a chart](docs/adding-a-chart.md)
- [Configure optional GitOps update automation](docs/gitops-update-automation.md)

## Release lifecycle

`Makefile` auto-discovers only direct children matching `<chart>/Chart.yaml`.
For both pull requests and `main`, CI runs repository hygiene and Helm validation
against every discovered chart. It then packages only charts changed by the
triggering commit. Pull requests stop there; a push to `main` publishes those
packages as immutable OCI artifacts under:

```text
oci://ghcr.io/makeitworkcloud/charts/<chart-name>
```

Publication can optionally be followed by a pull request that updates a GitOps
consumer to the new version. That automation is currently implemented only for
`opencode-server`; the generated pull request changes desired state but does not
deploy or sync Argo CD. See the [GitOps automation guide](docs/gitops-update-automation.md)
for the current contract and extension requirements.
