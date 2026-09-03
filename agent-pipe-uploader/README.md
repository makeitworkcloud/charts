# Agent Pipe uploader chart

This chart owns the internal `agent-pipe-uploader` Deployment and ClusterIP
Service. It is deliberately independent of `opencode-server` and exposes a
Streamable HTTP MCP endpoint at `/mcp`.

## Contract

The service listens only inside the cluster at
`http://agent-pipe-uploader.opencode.svc:8080/mcp` and has no TunnelBinding,
AWS credentials, or Kubernetes ServiceAccount token. It mounts only the
existing, cluster-owned artifact PVC; it can write a newly downloaded artifact
there but never mounts the OpenCode home PVC.

The MCP surface exposes `inspect_artifact`, `upload_artifact`,
`verify_download`, and `download_artifact`. Every remote transfer uses a
caller-supplied signed HTTPS URL. Each entry under `profiles` restricts its
allowed endpoints, object prefixes, authorization query parameters, and size
limit. The default `agent-pipe` profile permits only the private bucket's
approved regional hostname and `deliveries/` prefix.

The service rejects paths outside `/artifacts`, files over a profile's limit,
non-HTTPS URLs, URLs without the profile's required authorization parameters,
hosts outside a profile's `allowedHosts`, and object keys outside its
`pathPrefixes`. It does not log signed URLs or return them in results.

The presigned URL remains a bearer capability. Callers must obtain explicit
user approval before requesting an upload and must not send sensitive artifacts
to this service.

## Prerequisites

`kustomize-cluster` owns the `opencode` namespace and `opencode-artifacts` PVC.
The configured allowed hostnames must match the endpoint emitted by the AWS
presigning role; keep the host and `deliveries/` prefix restricted.

## Delivery

Publish this chart before adding its source to the OpenCode Argo CD
Application. Its OCI version is immutable. The initial GitOps consumer change
must remove the legacy `agent-pipe-uploader.yaml` resource in the same reviewed
revision so the existing `opencode` Application remains the sole owner of the
Deployment during the migration.

The chart intentionally retains the legacy `app=agent-pipe-uploader` Deployment
selector. Kubernetes selectors are immutable, so changing it would make the
GitOps migration fail instead of rolling the existing workload in place.
