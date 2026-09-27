# Agent Pipe uploader chart

This chart owns the internal `agent-pipe-uploader` Deployment and ClusterIP
Service. It is deliberately independent of `opencode-server` and exposes a
Streamable HTTP MCP endpoint at `/mcp`.

## Contract

The service listens only inside the cluster at
`http://agent-pipe-uploader.opencode.svc:8080/mcp` and has no TunnelBinding,
AWS credentials, or Kubernetes ServiceAccount token. It mounts the existing,
cluster-owned artifact PVC read-write for staging and approved exact-file
cleanup, but never mounts the OpenCode home PVC.

The MCP surface exposes `inspect_artifact`, `upload_artifact`,
`verify_download`, `download_artifact`, and
`remove_artifact(artifact, expected_sha256)`. Removal is local only: one exact
regular file whose full SHA-256 matches, never directories or symlinks, and
requires a separate exact permission prompt after verified retained delivery.
No S3 delete or native exec capability is added.

Every transfer uses a caller-supplied signed HTTPS URL. Every profile explicitly
lists allowed `operations` using the helper's `upload`, `download`, `verify`
names. Missing, malformed or unlisted operations fail closed in the new image.
Old images ignore this field and MUST NOT serve the vendor profile.

| Profile | Operations | Exact hosts | Path prefix | Maximum |
| --- | --- | --- | --- | --- |
| `agent-pipe` | upload, download, verify | `agent-pipe.s3.amazonaws.com`, `agent-pipe.s3.us-west-2.amazonaws.com` | `/deliveries/` | 100 MiB |
| `agent-presentations` | upload, download, verify | same bucket and hosts as `agent-pipe` | `/presentations/` | 100 MiB |
| `slidespeak-exports` | download, verify ONLY | `slidespeak-files.s3.amazonaws.com`, `slidespeak-files.s3.us-east-2.amazonaws.com` | `/` | 100 MiB |

All profiles require unique nonempty SigV4 query fields: `X-Amz-Algorithm`,
`X-Amz-Credential`, `X-Amz-Date`, `X-Amz-Expires`, `X-Amz-SignedHeaders`,
`X-Amz-Signature`. Preserve original URL signatures; never decode/re-encode
queries or follow redirects. Temporary-session signatures may also contain
`X-Amz-Security-Token`; leave it intact, but do not require it for non-session
signers. See [AWS SigV4 query authentication](https://docs.aws.amazon.com/AmazonS3/latest/developerguide/sigv4-query-string-auth.html).

The helper rejects unsafe artifact paths, symlink components, non-HTTPS URLs,
unapproved hosts/prefixes and transfers above 104857600 bytes. Downloads and
verification read the complete response and return measured `bytes` and
`sha256`; verification is not a one-byte probe. ETag or HeadObject alone is not
an integrity check. The helper does not log or return signed URLs or body bytes.

The artifact mount is trusted shared storage, not session isolation. Transfer
limits do not guarantee PVC capacity. Use sequential transfers, stop on capacity
failure, and never automatically delete or evict files. Cleanup is explicit
only after object verification and return of a durable reference.

## Blocking image and source gates

Chart 0.3.0 currently sets `image.tag` to
`63ccfde32e70decf81255e816cd2ada57b4f7e10`, the UNPUBLISHED source branch head in
`makeitworkcloud/images`. This is a STAGING-ONLY BLOCKED PLACEHOLDER, not proof
that an image exists. Before chart merge, replace it with a verified
main-published immutable image SHA (optionally digest-qualified), recording the
successful image publication and registry identity in the future PR. A squash
merge produces a different SHA. Never use `latest`. CI rendering cannot prove
publication, and this branch must not be deployed as-is.

The [SlideSpeak download docs](https://docs.slidespeak.co/v1/reference/download)
show the global `slidespeak-files.s3.amazonaws.com` host and refresh by
`request_id`; they do not prove the exact path, regional host or signing fields
of every live export. Before enabling vendor transfers, verify safe metadata
from an actual tool-produced export response: HTTPS, exact allowed hostname,
nonempty object path, required query field names, no credentials printed.
Stop on mismatch; do not broaden the profile or generate a deck just to test it.

`Recreate` deliberately trades availability for no old/new helper overlap
during Deployment updates. Stop in-flight transfers before the separately
approved rollout. Existing pods load profiles at startup; the checksum restarts
them, but verify all old pods are gone and the new image/profile behavior before
allowing vendor use. Recreate is not a runtime authorization proof or a defense
against arbitrary concurrent writers.

## Prerequisites and delivery

`kustomize-cluster` owns the namespace and `opencode-artifacts` PVC. Applied
storage policy and role access must support private 90-day `presentations/`
retention while preserving one-day `deliveries/`. No infrastructure is created
by this chart. Follow [Retained presentation rollout](../docs/retained-presentation-artifacts.md)
for the producer/consumer release gates, including the manual uploader 0.3.0
GitOps pin BEFORE OpenCode 0.4.7's existing automatic pin workflow.

The chart retains the legacy `app=agent-pipe-uploader` selector. During an initial
migration the consuming revision must remove the legacy standalone manifest so
the existing `opencode` Application remains the sole owner. Do not duplicate
ownership or change the immutable Deployment selector.
