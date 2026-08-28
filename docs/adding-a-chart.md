# Adding a chart

Add each chart as a direct child of this repository. The release workflow
discovers `<chart>/Chart.yaml`; deeper or grouped chart directories are not
included.

For the consuming GitOps resources, follow the
[kustomize-cluster workload guide](https://github.com/makeitworkcloud/kustomize-cluster/blob/main/docs/adding-a-workload.md).

## Create the chart

Use this structure:

```text
<chart>/
  Chart.yaml
  README.md
  values.yaml
  templates/
  files/        # optional
```

An application chart should declare at least this metadata:

```yaml
apiVersion: v2
name: <chart-name>
description: <short purpose>
type: application
version: 0.1.0
appVersion: "<workload-version>"
```

- Keep the directory and chart `name` aligned. The metadata name becomes the
  OCI package name.
- Use a valid semantic version for `version`. Bump it for every change to a
  previously published chart, including templates and files; published OCI
  versions are immutable.
- Set `appVersion` to the packaged workload version when one exists. Quote it
  so YAML does not reinterpret the value.

## Preserve ownership boundaries

The chart should own portable workload resources such as Deployments and
non-secret application ConfigMaps. A workload-specific Service may also be
chart-owned when that is part of the agreed consumer contract.

By default, `kustomize-cluster` continues to own Secrets, Namespaces,
persistent storage, shared Services or networking, TunnelBindings, and
cluster/operator resources. Do not define the same resource in both
repositories. Document prerequisites and any intentional ownership migration
in the chart README and the consuming GitOps pull request.

## Organize configuration

- Put safe defaults and consumer overrides in `values.yaml`. Never put
  credentials, tokens, kubeconfigs, or decrypted secret values there.
- Keep Kubernetes manifests in `templates/`. Use `_helpers.tpl` for repeated
  naming and labels when useful, and ensure default values render successfully.
- Put packaged, non-secret static content in `files/` only when templates load
  it through Helm's `.Files` API. A file change is a chart content change and
  requires a new chart version.
- Add `<chart>/README.md` with the chart purpose, ownership boundary,
  prerequisites, important values, rendered resources, and consumer example.
  Keep operational and cluster rollout procedures in their canonical guides
  rather than duplicating them.

Update the chart index in the root [README](../README.md) when adding or
removing a chart.

## Validate locally

Install Git, Helm, `jq`, pre-commit, and GNU `find` before using the repository
Make targets. Linux environments normally provide the required `find`
implementation. On macOS, put GNU findutils ahead of BSD `find` on `PATH`; if
that is not available, use the chart-specific Helm commands below and rely on
Linux CI for repository-wide discovery.

Run the same inexpensive checks used by CI when the tools are available:

```bash
pre-commit run --all-files
make test
helm lint --strict <chart>
helm template test <chart> >/dev/null
destination="$(mktemp -d)"
make package-chart CHART=<chart> DESTINATION="$destination"
```

`make test` lints and renders every discovered chart. The chart-specific
commands make failures easier to isolate, and packaging confirms the archive
can be built without publishing it.

## Open the pull request

Before requesting review, confirm:

- The chart is a direct child with complete `Chart.yaml` metadata and a chart
  README.
- The chart version has never been published, or was bumped for this change.
- Rendered resource names, namespaces, values, and ownership match the intended
  GitOps consumer.
- No secret or decrypted material is present.
- Local validation passed, or the pull request states which checks could not be
  run.
- The root chart index and any affected consumer documentation are updated.

CI validates repository hygiene and every discovered chart on both pull
requests and `main`. Separately, `changed-charts` compares changed top-level
paths to the discovered chart list, so only changed charts are packaged. On a
pull request this proves packaging only; no OCI artifact is published.

## Publish and verify

After review and merge, the `main` workflow packages changed charts and pushes
them to GHCR. The package coordinates are:

```text
repository: ghcr.io/makeitworkcloud/charts
chart:      <Chart.yaml name>
version:    <Chart.yaml version>
OCI URI:    oci://ghcr.io/makeitworkcloud/charts/<chart-name>
```

Confirm the `package <chart>` job succeeded, then inspect the published
metadata with authenticated GHCR access when required:

```bash
helm show chart oci://ghcr.io/makeitworkcloud/charts/<chart-name> \
  --version <version>
```

Verify that the returned `name` and `version` match `Chart.yaml` before a
consumer pins the artifact.

If pull request validation or packaging fails, fix the cause and push another
commit. If a `main` publication fails before the artifact exists, correct the
transient or configuration failure and rerun the failed job. If publication
status is uncertain, check GHCR first: never change or republish content under
an existing version. Any content correction requires a new version.

Publication alone does not update a cluster. A chart may opt into the optional
[post-publish GitOps pull request](gitops-update-automation.md), but that
automation must be implemented explicitly for each chart.
