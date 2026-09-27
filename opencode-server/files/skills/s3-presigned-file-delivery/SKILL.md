---
name: s3-presigned-file-delivery
description: Use when the user asks to download, share, or get a fresh link to a retained S3 artifact, or to hand a session artifact to storage through a presigned URL.
---

# S3 presigned file delivery

Use the direct `aws` MCP for metadata and presigning and the existing
`agent-pipe` MCP for bytes. Apply `cloud-artifact-transfer` boundaries and exact
transfer/removal approvals. No new service, credentials, native exec or S3
DeleteObject permission is granted.

## Retention and preflight

The private `agent-pipe` bucket supports two separate intended policies:
`deliveries/` via profile `agent-pipe` keeps its one-day expiration;
`presentations/` via profile `agent-presentations` makes owner-approved,
user-directed non-sensitive decks eligible for expiration after 90 days.
Retention is not a 90-day signed URL and lifecycle expiration is asynchronous,
not an exact purge guarantee. Do not store submissions or sensitive documents.
Never presign or link `mitw-tf-*-infra` state buckets.

Before storing, use the direct AWS MCP to confirm the approved account identity,
bucket owner and actual region, all four effective Public Access Block controls,
no public bucket policy/ACL access, encryption at rest and bucket-owner-enforced
ownership. Verify the applied lifecycle rules cover `presentations/` at 90 days
without a broader/overlapping earlier expiration, and preserve `deliveries/`
at one day. Verify bucket versioning and exact-key versions/delete markers:
unexpected existing versions or versioning outside the approved retention
contract block the write. If enabled, noncurrent-version expiration must also
be explicitly approved and bounded; do not assume current-object expiry removes
older versions. Use a new collision-resistant key, not overwrite/reuse.
Confirm the managed role's intended PutObject/GetObject and metadata access
for that prefix. Successful presigning is not proof of permissions or storage.
Absent infrastructure/profile/image prerequisites mean archive INCOMPLETE;
retain `request_id` and offer temporary vendor delivery, not a persisted claim.
Never alter IAM, lifecycle, ACLs or versioning to get past a failure.

Use `presentations/<session-id>/<artifact-id>/presentation.pptx`. The session ID
must be actual trusted session metadata, or a newly allocated unique delivery
token explicitly labeled as such if unavailable; never guess. Do not embed
names, application details or sensitive data. The staging relative path is the
same under `/artifacts`. The helper supports only approved exact S3 hosts;
stop if the verified region's generated endpoint does not match the profile.

## Upload and tested delivery

1. Confirm a regular non-sensitive staged file, positive size at most 104857600
   bytes for decks, and SHA-256 via `agent-pipe_inspect_artifact`. Compare with
   the download result when staged from SlideSpeak.
2. Obtain exact upload approval for artifact, bucket/key, profile and retention.
   Mint a PUT using `aws_aws___get_presigned_url`, `operation: upload`, the
   verified region and `expires_in: 900`. Do not add `s3_params` requiring
   headers the helper cannot send. Pass the original URL unchanged to
   `agent-pipe_upload_artifact`; the exact permission prompt remains required.
3. Compare a fresh local inspection with the original bytes/hash and upload
   byte count. Use `aws_aws___run_script` for `HeadObject` of the exact key;
   check ContentLength, encryption, LastModified, VersionId and safe metadata
   against the intended upload and approved versioning. Never return raw object
   bytes or credentials. ETag is not a SHA-256 integrity check.
4. Mint a GET with `operation: download`, the same bucket/key/region and
   `expires_in: 900`. Call `agent-pipe_verify_download` with the storage profile
   and exact unchanged URL. Require a full-body `bytes` and `sha256` match to
   the staged file. Do not substitute HEAD, curl, a fetch tool or URL rewriting.
5. Only on success return the SAME tested URL as `[Download presentation](url)`
   with an approximately 15-minute expiry (or less if signing credentials expire
   sooner). This transient tested S3 GET is the sole exception to the generic
   no-signed-URL-output rule. Never save the URL in a file or durable record.
6. Return a durable reference `s3://<bucket>/<key>` with region, `request_id`,
   measured bytes, SHA-256, creation time and requested `retention_days: 90`
   for presentations. Record only this non-sensitive metadata in the session's
   authorized record, not signed URLs, source documents or submissions. Report
   requested retention separately from verified applied lifecycle evidence.
7. Only after verified storage and returning that durable reference may the
   user approve `agent-pipe_remove_artifact` for the exact staged path and hash.
   No automatic local cleanup or S3 deletion is allowed.

## Fresh links and bounded failure handling

On a later request, recover the bucket/key/region and expected bytes/hash from
the durable record, recheck access and exact-object metadata, mint a fresh
900-second GET and fully verify it against the recorded identity before
returning that tested link. Do not regenerate or re-upload the presentation.
If the record is missing, ask for its reference; never guess a key or digest.
If the object is expired/missing or changed, report it rather than claiming the
archive still exists or silently accepting replacement bytes.

Allow at most one fresh signed URL and one sequential retry per failed transfer
or verification for expiry/transient errors, never for an unresolved permission,
profile, hash or capacity failure. After an ambiguous PUT, inspect the exact
key first; if already correct, verify and deliver without a second PUT. A
changed object or unexpected versions block retry. Never fall back to public
storage, alter signatures, or hand out an untested link. Signed URLs are bearer
capabilities; short expiry is not revocation. Do not claim they cannot be
invalidated by credential or policy changes.
