---
name: arc-runner-diagnostics
description: Use when GitHub Actions jobs queue, ARC runners fail, or runner-controller and runner-scale-set resources need investigation.
---

# ARC runner diagnostics

1. Locate the runner-controller and runner-scale-set Argo CD applications and inspect sync/health first.
2. Inspect ARC custom resources, listener and runner pods, namespace events, logs, and resource pressure.
3. Correlate findings with the GitHub workflow job, its runner labels, and PR check runs.
4. Treat stale listener or EphemeralRunner resources as a diagnostic finding; do not delete, restart, scale, or sync them without confirmation.

State whether the blocker is GitHub scheduling, ARC reconciliation, pod scheduling, image pull, or workload execution.
