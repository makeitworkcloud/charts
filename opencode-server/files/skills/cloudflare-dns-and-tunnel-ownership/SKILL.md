---
name: cloudflare-dns-and-tunnel-ownership
description: Use when changing or diagnosing Cloudflare DNS, TunnelBinding, ClusterTunnel, Access, or tunnel-route ownership.
---

# Cloudflare ownership

Manage desired state through OpenTofu and GitOps, never manual host configuration.

- `tfroot-cloudflare` owns bootstrap and non-tunnel Cloudflare infrastructure.
- `kustomize-cluster` TunnelBinding resources own workload tunnel routes, proxied CNAMEs, and their ownership TXT records.
- Bootstrap `api` and `k3s` names remain OpenTofu-owned with TunnelBinding DNS updates disabled.

For `unmanaged FQDN present`, identify the current owner before proposing a change. Never expose tunnel JSON, certificates, API tokens, or unredacted credentials.
