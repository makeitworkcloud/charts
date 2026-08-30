# Post-publish GitOps update automation

The release workflow can optionally open a pull request that pins a GitOps
consumer to a newly published chart version. This step is not generic today:
`.github/workflows/helm.yml` contains an `opencode-server`-specific job and
script. Adding another direct-child chart does not opt it into this automation.

The generated pull request changes Git desired state. The workflow enables
GitHub auto-merge on it, so it squash-merges itself once the destination
repository's required checks pass. The workflow does not sync Argo CD, and the
merge does not prove rollout health; verify reconciliation separately.

## Current OpenCode contract

The `update-opencode-gitops` job runs only after a successful `main` package job
that included `opencode-server`. Its hard-coded chart-to-destination mapping is:

| Contract field | Current value |
| --- | --- |
| Chart directory and metadata name | `opencode-server` |
| Published OCI repository | `ghcr.io/makeitworkcloud/charts` |
| Destination | `makeitworkcloud/kustomize-cluster` (`main`) |
| Destination manifest | `workloads/apps/opencode-app.yaml` |
| Helm source | `opencode-server` in `ghcr.io/makeitworkcloud/charts` |
| Updated field | That source's single `targetRevision` |
| Automation branch | `automation/opencode-server-<version>` |
| Merge behavior | GitHub auto-merge, squash, gated on destination required checks |

The script reads the version from `opencode-server/Chart.yaml`, requires
exactly one matching Helm source, updates only its `targetRevision`, commits the
change when needed, and creates a pull request if that branch has no open pull
request.

The job, condition, chart path, destination repository, manifest path, source
matcher, branch, commit, and pull request text are all OpenCode-specific
literals. They are not a reusable chart-to-consumer configuration model.

## Authentication and permissions

The job creates a short-lived GitHub App installation token scoped to the
destination repository. The App requires repository contents and pull request
write permissions; the workflow job itself otherwise retains read-only source
repository permissions.

The App private key is supplied through the charts repository Actions secret
`CHART_UPDATER_GITHUB_APP_PRIVATE_KEY`, which is managed by `tfroot-github`.
It is not retrieved from AWS. Never copy the key or secret payload. Keep the
non-secret App identifier in the canonical workflow configuration rather than
duplicating it in documentation or unrelated code, and read installation
identifiers from GitHub when needed. Follow the
[tfroot-github chart updater App runbook](https://github.com/makeitworkcloud/tfroot-github/blob/main/docs/chart-updater-github-app.md)
for installation scope, provisioning, and rotation.

## Branch and pull request behavior

- A version-specific branch is created from the destination's current `main`
  only when the branch does not already exist.
- An existing branch is reused; the workflow does not rebase or reset it.
- The destination file must contain exactly one expected chart/repository
  source. Zero or multiple matches fail without editing the file.
- The workflow commits only when `targetRevision` changes.
- An existing open pull request for the branch is reused. If none exists, the
  workflow creates one with the version in its title and body.
- After the pull request exists, the workflow enables GitHub auto-merge with
  the squash method unless it is already enabled. GitHub performs the merge
  once the destination's required checks pass under the protections managed
  centrally by `tfroot-github`.
- Auto-merge requires the destination repository's `allow_auto_merge` setting,
  which `tfroot-github` manages in `gh-repositories.tf`. If the setting is
  disabled or the App cannot merge under the destination's push restrictions,
  the job fails after publication; the published artifact remains valid and
  the pull request stays open for manual handling.
- Required checks are strict, so a destination `main` commit landing between
  check success and merge stalls the merge until the automation branch is
  updated. The workflow does not update the branch; resolve by updating the
  branch and letting checks rerun, or by rerunning the job after a reviewed
  cleanup.

These properties make a retry safe in the usual partial-failure cases, but a
stale or manually modified automation branch may require a reviewed cleanup
before retrying.

## Add another chart safely

1. Publish the chart normally and add its consuming Argo CD Application by
   following the
   [workload guide](https://github.com/makeitworkcloud/kustomize-cluster/blob/main/docs/adding-a-workload.md).
2. Define an explicit chart-to-destination contract: chart directory and name,
   OCI repository, destination repository/base/path, exact source matcher,
   target field, and branch/PR naming.
3. Add a dedicated job or refactor the workflow to use an explicit allowlisted
   mapping. Update the changed-chart condition, `Chart.yaml` path, destination
   literals, matcher, and branch/commit/PR text. Do not broaden the regex to
   update arbitrary `targetRevision` fields.
4. Preserve the invariant that the updater runs only on `main`, only after that
   chart was packaged successfully, and only after publication.
5. Keep the one-match assertion and least-privilege token scope. If the
   destination is not already in the GitHub App installation and token request,
   update `tfroot-github` through its runbook rather than adding another secret
   source. Confirm through `tfroot-github` whether the destination belongs in
   the auto-merge repository list.
6. Link the chart README to the consumer and record whether GitOps updates are
   automated or manual.

Before merge, validate workflow syntax and test the update logic against the
expected destination manifest or a fixture. Cover the intended one-match
update, zero matches, multiple matches, and an already-current version. The
pull request workflow can validate and package the changed chart, but the
post-publish job's `main` condition means its repository write cannot be tested
end to end from a pull request.

## Failure and retry

If chart packaging or publication fails, the updater does not run. Resolve the
release failure and verify the OCI artifact as described in
[Adding a chart](adding-a-chart.md).

If publication succeeded but the updater failed, the artifact remains valid
and nothing was deployed. Correct the token, permission, matcher, branch, or API
failure, then use the workflow's failed-job retry. A retry reuses an existing
version branch and open pull request. If the destination already pins the
version, verify whether a pull request is still necessary; creating a pull
request from a branch with no diff will fail.

After the pull request is created, `kustomize-cluster`'s required checks gate an
automatic squash merge; no approval requirement applies to these automation
pull requests. If checks fail, the pull request stays open for diagnosis. After
the merge, follow the
[rollout and rollback guide](https://github.com/makeitworkcloud/kustomize-cluster/blob/main/docs/rollout-and-rollback.md)
to verify reconciliation and health or to return to a previous immutable
version.
