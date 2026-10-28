---
name: libvirt-host-and-vm-recovery
description: Use when diagnosing tfroot-libvirt VM, volume, cloud-init, SSH, libvirt-network, or host-firewall recovery issues.
---

# Libvirt recovery

Collect repository, CI-plan, Argo/Kubernetes, and available read-only diagnostic evidence before proposing recovery.

## Ownership and execution boundary

For changes owned by `tfroot-libvirt`, use its reviewed OpenTofu workflow rather than manual host or guest commands. Do not use SSH to bypass IaC ownership for VM replacement, volume deletion, network or firewall configuration, imports, state repair, or taints. Never run local OpenTofu init, plan, apply, destroy, import, taint, or state operations from this server; use authorized CI and the canonical repository's recovery procedure.

This is not a blanket SSH prohibition. Use the configured `hero-ssh` MCP for authorized, bounded read-only host diagnostics. Separate owner-directed host work, including live migration outside the `tfroot-libvirt` workflow, is not prohibited merely because that repository will be updated afterward. Establish the actual ownership and scope first; if uncertain, ask before acting. Do not use an operational task as a pretext to make configuration changes owned by IaC.

Before any live mutation, explain the smallest reviewed procedure, its risks and recovery path, and obtain explicit confirmation of the exact operation and target. Diagnostic authorization is not mutation authorization; prior approval covers only its stated scope. Honor SSH tool policy and privilege gates, and never retrieve secrets, credentials, state, kubeconfig material, sensitive plans, or raw live-system payloads. Report only bounded, non-sensitive evidence.

Verify the target host's active network and firewall-zone behavior from authoritative host or runtime evidence before proposing a firewall remediation. Do not assume either `libvirt`-zone or `public`-zone behavior.
