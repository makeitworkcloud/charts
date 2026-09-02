# GitHub Actions OpenCode runner instructions

You are running in an ephemeral GitHub Actions runner with a checkout of the
repository that triggered this workflow. Apply that repository's `AGENTS.md`
and task-relevant documentation before editing files.

## Runner boundary

- The production OpenCode server's Kubernetes MCP proxies are intentionally not
  configured here. Do not assume cluster, AWS, Argo CD, Grafana, Kubernetes,
  or SSH access.
- Treat secrets, tokens, decrypted values, private keys, kubeconfigs, state,
  and sensitive plan output as unavailable. Never add them to repository files,
  logs, issues, pull requests, or comments.
- Do not deploy, publish, merge, dispatch another workflow, or mutate a live
  system. Propose such work for explicit confirmation.
- Make changes only in the checked-out repository. Do not create, push, or
  open pull requests manually: `opencode github run` handles branch and pull
  request delivery after the session completes.
- The workflow supplies GitHub event context and authentication. Do not claim
  that an unavailable GitHub MCP or other MCP integration was used.

## Validation and reporting

Use the repository's authoritative CI and guidance. Report only checks and
outcomes actually available from the workflow; distinguish authored changes
from validation, publication, deployment, and functional verification.
