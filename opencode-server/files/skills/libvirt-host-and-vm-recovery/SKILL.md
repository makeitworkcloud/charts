---
name: libvirt-host-and-vm-recovery
description: Use when diagnosing tfroot-libvirt VM, volume, cloud-init, SSH, libvirt-network, or host-firewall recovery issues.
---

# Libvirt recovery

Collect repository, CI-plan, Argo/Kubernetes, and available read-only diagnostic evidence before proposing recovery.

Do not perform host changes, SSH commands, imports, state repair, volume deletion, VM replacement, firewall changes, taints, or direct apply operations from this server. Explain the smallest reviewed recovery path and obtain explicit confirmation before any live operation.

Verify the target host's active network and firewall-zone behavior from authoritative host or runtime evidence before proposing a firewall remediation. Do not assume either `libvirt`-zone or `public`-zone behavior.
