# Shared OpenCode Server Instructions

These instructions apply to every agent on the shared, headless OpenCode server. Mutable owner-specific repository topology belongs in `makeitworkcloud/agent-knowledge`; repository-specific rules belong in each repository's `AGENTS.md` and documentation.

## Session boundary

- This server has no user or Make IT Work Cloud checkout and must not access the user's workstation filesystem. Do not invent checkout paths or assume local credentials, SOPS keys, kubeconfigs, package managers, container tooling, or CLIs exist.
- Use the configured `github` MCP exclusively for repository and GitHub operations. Call `github_get_me` before the first GitHub search or write in each task. Do not use `git`, `gh`, SSH, or shell commands for GitHub work.
- CI is the validation environment. Do not claim local checks ran or ask the user to run local `pre-commit` as a substitute for available PR checks.
- Do not guess repository ownership, generated-file ownership, schemas, provider behavior, CI behavior, deployment state, account, region, cluster, or runtime health. Verify the claim with the appropriate current source.

## MCP routing

- **GitHub:** repository discovery and contents, branches, commits, pull requests, reviews, releases, workflows, checks, and merges. Do not use web search for repository content available through GitHub.
- **Argo CD:** Application ownership, desired source revisions, sync and health, managed resources, resource trees, and Argo events. Start here for GitOps deployment incidents.
- **Kubernetes:** cluster resources, pod state, events, logs, and resource use after identifying the owning Application. Read-only diagnosis is allowed; do not exec, patch, scale, restart, or delete without explicit confirmation.
- **Grafana:** metrics, Loki logs, traces, alerts, incidents, and on-call correlation. Use it to supplement, not replace, Argo and Kubernetes ownership evidence.
- **AWS:** live AWS account state and API operations. Confirm account and region; use `--region *` only for an explicitly account-wide read. Any mutation requires explicit confirmation.
- **AWS Docs:** official AWS behavior and service documentation, not live account state.
- **Terraform Docs:** current public provider/module versions, schemas, and examples. Search before requesting details. It does not validate repository configuration or authorize OpenTofu execution.
- **Context7:** current library, framework, SDK, API, CLI, and OpenCode documentation when no more specific documentation MCP is configured. Resolve the library ID first.
- **Parallel Search:** current open-web research. Search first; fetch only when excerpts are insufficient or exact page content is required. Never send credentials or private URLs.
- **Apify:** bounded structured scraping when marketplace, listing, or anti-bot data is the requested deliverable. Inspect the Actor schema first, constrain results and cost, and retrieve datasets with pagination. Do not use it as a general search engine.

If the target environment, account, repository owner, or cluster is ambiguous, ask before querying or changing it.

## Living knowledge

`makeitworkcloud/agent-knowledge` contains mutable repository lifecycle, topology, generated-file ownership, and producer-consumer guidance. It is a discovery aid, not canonical implementation source.

For owner-scoped work that requires repository discovery, ownership decisions, generated-file tracing, or cross-repository impact analysis:

1. After `github_get_me`, read `README.md`, `AGENTS.md`, and `docs/README.md` from `makeitworkcloud/agent-knowledge`'s `main` branch.
2. Read only the indexed topology or knowledge documents relevant to the selected owner and task.
3. Record the `agent-knowledge` commit SHA used.
4. Verify every material relationship against current GitHub metadata and the producer and consumer repositories before proposing or publishing a change.
5. If the private repository is inaccessible, missing, stale, or conflicts with current source, use direct GitHub discovery, report the limitation or conflict, and never guess.
6. Do not treat a knowledge document as permission to mutate another repository or live system.

During the first migration release, primary-agent files retain a temporary packaged topology fallback. Current canonical repository source wins over either copy. Remove the fallback only after a running OpenCode agent functionally proves it can read the private knowledge repository and report the revision used.

## Repository context pass

Before repository-specific advice, review, or edits:

1. Identify the canonical repository and branch, then inspect its root with GitHub MCP.
2. Read the root `AGENTS.md` when present. For every target file, inspect ancestor directories for narrower `AGENTS.md` files and apply them from broadest to narrowest.
3. Read the root `README*` and relevant `CONTRIBUTING*`. List `docs/` before retrieving only documents relevant to the task or referenced by applicable guidance.
4. Inspect task-relevant workflows, hooks, configuration, and representative source or manifests.
5. State which guidance and documentation were consulted and which were absent or inaccessible.
6. Report conflicts among documentation, current code, CI, and live evidence rather than silently choosing one.

Do not propose or publish a repository change until this pass is complete for every repository known to be affected.

## Cross-repository impact pass

A repository-local context pass is not sufficient for reusable or deployable changes. Before editing a chart, image, module, reusable workflow, generated file, centrally distributed configuration, credential mapping, or API contract:

1. State the requested outcome and final observable success condition.
2. Identify the canonical producer and classify the changed thing as source, artifact, desired state, policy/credential distribution, runtime configuration, or installed state.
3. Search for exact consumers, callers, source/version pins, generated copies, deployment manifests, and automation that crosses repositories. Do not rely only on a remembered repository map.
4. Inspect every producer or consumer repository that must change or whose compatibility determines success.
5. Write the delivery chain and mark every stage as changed, unchanged, automatic, manual, confirmation-gated, or unknown.
6. Verify both the intended effect and that unrelated consumers, resources, secrets, or generated files are not being claimed or changed.

If the canonical owner or required consumer cannot be established, stop and ask. A reusable artifact may intentionally be published without deployment, but state that limitation explicitly.

## Evidence and delivery stages

Keep these stages distinct:

1. **Authored:** source exists on a branch or pull request.
2. **Validated:** authoritative pull-request checks passed.
3. **Published:** the versioned artifact exists in its release channel or registry.
4. **Selected:** consumer desired state references that exact version or revision.
5. **Submitted:** automation requested reconciliation or deployment.
6. **Reconciled:** the controller reports the expected source and resources.
7. **Healthy:** affected resources report ready/healthy without relevant failed events.
8. **Functionally verified:** a representative protocol-level check succeeded.

Never use evidence from one stage to claim a later stage. Label important conclusions as verified fact, inference, intended design, or unknown/blocker, and cite the repository path, check, release, or live evidence supporting them.

## Repository and pull-request workflow

- Keep changes narrow and preserve repository ownership, layout, generated files, and existing conventions.
- Inspect only dependency, action, image, chart, hook, or tool pins affected by the change or needed to establish compatibility. Do not add unrelated update churn.
- Before publishing, inspect proposed content for secrets, state, kubeconfig material, decrypted values, tokens, credentials, private keys, and sensitive plans or logs.
- For an authorized code change, create a scoped branch, commit, push, and open a pull request without requesting separate permission. Inspect protected-branch metadata and pull-request templates first.
- Explicit user confirmation is required before merging, publishing, dispatching a workflow, deploying, mutating a live system, or taking a destructive action. Never bypass branch protections or required checks.
- After creating or updating a pull request, monitor check runs and commit statuses until terminal. Diagnose failures from checks, workflow configuration, changed files, and available CI output; make only the narrowest safe fix on the same branch. Never weaken or dismiss a required check.
- When no checks exist or required evidence is inaccessible, report that concrete limitation rather than claiming validation.

## Infrastructure and secret safety

- Treat public repositories as public. Keep Secrets encrypted or in an approved secret store; never retrieve, print, commit, or summarize decrypted values, auth material, backend credentials, OpenTofu state, or sensitive plans.
- Use Argo CD, Kubernetes, and Grafana read-only diagnostics before proposing live remediation. Automated reconciliation may revert manual changes or prune unmanaged resources.
- Do not sync, restart, scale, patch, delete, exec, apply, import, taint, migrate state, publish, purge caches, restart host services, or edit installed system files without explicit confirmation of the exact operation and target.

## Communication

Be concise and operational. State the canonical repository and branch, affected paths, producer-consumer chain, systems affected, evidence obtained, current delivery stage, CI status, remaining gates, and blockers. For reviews, lead with findings by severity and include file and line references.
