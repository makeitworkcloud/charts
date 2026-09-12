# OpenCode MCP routing

OpenCode is an in-cluster MCP consumer. It connects directly to the configured
ToolHive backend proxy Services in the `mcp` namespace; those client entries
are canonical in [`../files/opencode.json`](../files/opencode.json).

The `vmcp-gateway` VirtualMCPServer is reserved for external consumers. Do not
add it as an OpenCode MCP client and do not expose duplicate aggregate and
direct entries to OpenCode: duplicate tool namespaces make tool selection
ambiguous.

Backend Services remain owned by `makeitworkcloud/kustomize-cluster` under
`workloads/mcp-gateway`. This chart owns only OpenCode's non-secret client URLs.
It must not add proxy credentials, external routes, or gateway membership.

## Delivery and verification

A routing change updates packaged OpenCode configuration and requires a chart
version bump. After chart PR validation and a confirmed merge, publication and
the generated `kustomize-cluster` chart-pin PR are separate stages. Before
selecting a GitOps pin, require all 14 direct ToolHive proxy Services (`apify`,
`argocd`, `aws`, `aws-docs`, `cloudflare`, `context7`, `gcp`, `grafana`,
`kubernetes`, `parallel-search`, `playwright`, `slidespeak`, `terraform-docs`,
and `twilio-docs`) to be reconciled and healthy. After the selected pin is
reconciled, verify a fresh OpenCode session discovers the direct integrations
and performs bounded read-only representative calls. Do not infer runtime
reachability from chart CI.

A rollback to a gateway- or member-dependent chart revision requires the
external-only `vmcp-gateway` and every required gateway member to be available
before selecting the rollback pin. Verify their availability as part of the
rollback rollout; do not assume the direct-proxy prerequisites cover an
aggregate-era revision.
