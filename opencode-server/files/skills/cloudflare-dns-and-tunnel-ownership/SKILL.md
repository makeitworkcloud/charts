---
name: cloudflare-dns-and-tunnel-ownership
description: Use when changing or diagnosing Cloudflare DNS, TunnelBinding, ClusterTunnel, Access, or tunnel-route ownership.
---

# Cloudflare ownership

Manage desired state through its canonical OpenTofu or GitOps owner, never manual host or console configuration.

Before proposing a change, consult the relevant Make IT Work Cloud topology knowledge and verify the current canonical repository guidance and source. Identify whether the affected FQDN or route is bootstrap, non-workload, or workload-managed; do not infer ownership from the hostname alone.

For an `unmanaged FQDN present` finding, establish the current owner before proposing a change. Never expose tunnel JSON, certificates, API tokens, or unredacted credentials.
