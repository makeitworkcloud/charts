---
name: argo-kubernetes-incident-triage
description: Use when investigating Argo CD application health, deployment failures, Kubernetes pods, events, logs, or resource pressure.
---

# Argo and Kubernetes triage

Use read-only tools in this order:

1. Read the Argo CD Application and resource tree.
2. Inspect managed resource health and relevant application events.
3. Inspect pod status, namespace events, container logs, and resource use.
4. Use Grafana for metrics, logs, traces, alerts, or on-call correlation.

Do not sync, restart, scale, patch, delete, or run resource actions without explicit confirmation. Report affected application, resources, evidence, and the least-invasive proposed remediation.
