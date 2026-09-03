# Agent Pipe uploader chart

This chart owns the internal `agent-pipe-uploader` Deployment and ClusterIP
Service. It is deliberately independent of `opencode-server`.

## Contract

The service listens only inside the cluster at
`http://agent-pipe-uploader.opencode.svc:8080` and has no TunnelBinding, AWS
credentials, or Kubernetes ServiceAccount token. It mounts only the existing,
cluster-owned artifact PVC read-only.

`POST /v1/upload` accepts this JSON request:

```json
{"artifact":"report.pdf","url":"<presigned-S3-PUT-URL>"}
```

The uploader rejects paths outside `/artifacts`, files over `upload.maxBytes`,
non-HTTPS URLs, URLs without S3 SigV4 query parameters, hosts outside
`upload.allowedHosts`, and object keys outside `upload.keyPrefix`. It does not
log request bodies or return the presigned URL.

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
