---
name: libvirt-host-and-vm-recovery
description: Use when diagnosing tfroot-libvirt VM, volume, cloud-init, SSH, libvirt-network, or host-firewall recovery issues.
---

# Libvirt recovery

Collect repository, CI-plan, Argo/Kubernetes, and available read-only diagnostic evidence before proposing recovery.

Do not perform host changes, SSH commands, imports, state repair, volume deletion, VM replacement, firewall changes, taints, or direct apply operations from this server. Explain the smallest reviewed recovery path and obtain explicit confirmation before any live operation.

Remember that libvirt guest traffic reaches the host through the `libvirt` firewalld zone; do not infer host `public`-zone behavior from it.
