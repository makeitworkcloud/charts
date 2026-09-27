---
name: s3-presigned-file-delivery
description: Use when the user asks to download, share, or get a fresh link to an S3 object, or to hand a non-sensitive session artifact to storage through a presigned URL.
---

# S3 presigned file delivery

Use the direct `aws` MCP for metadata/presigning and `agent-pipe` for bytes.
Apply `cloud-artifact-transfer` boundaries and exact transfer/removal prompts.
No credentials, new service, native exec or S3 DeleteObject permission is added.

## Select the policy first

- Ordinary new artifacts: profile `agent-pipe`, private bucket `agent-pipe`,
  `deliveries/<session-id>/<artifact-id>/<filename>`, retention_days: 1.
  Preserve the actual filename extension. Do not require presentation lifecycle,
  SlideSpeak request IDs, vendor profiles or presentation-image readiness for
  ordinary delivery; verify only capabilities needed by the selected operation.
- Retained generated decks: profile `agent-presentations`, SAME bucket,
  `presentations/<session-id>/<artifact-id>/presentation.<ext>`,
  retention_days: 90. This policy is only for user-directed non-sensitive decks
  whose retained delivery the owner accepts. From the verified generation
  request, `response_format: powerpoint` selects `pptx` and
  `response_format: pdf` selects `pdf`. Confirm the documented default if
  omitted. Never infer format from an untrusted filename/URL or expand bytes.
- Existing S3 GET requests: use the exact authorized bucket/key/region and
  matching configured profile, without re-upload, rename or retention change.
  Do not require presentation-specific lifecycle, SlideSpeak, upload or cleanup
  prerequisites for a generic existing-object GET. Never invent a profile or
  use an arbitrary bucket; another bucket requires explicit direction AND a
  matching approved profile. Never presign `mitw-tf-*-infra` state buckets.

For new keys use trusted actual session metadata, or allocate and explicitly
label a unique delivery token if unavailable; never guess a session ID. Use a
collision-resistant artifact ID, no personal/application details. Staging paths
are the same relative paths under `/artifacts`. Retention describes lifecycle
eligibility, not signed-link lifetime or an exact purge guarantee.

## Applicable preflight

For all operations confirm the authorized account, bucket owner, actual region,
private access and exact key through the AWS MCP. Verify the generated endpoint
matches the selected profile. Presigning success is not proof of permissions.
For existing GETs check GetObject access and HeadObject metadata; compare any
recorded expected bytes/SHA-256. Without a prior digest, full GET verification
establishes the current observed identity, NOT historical identity. Return that
distinction with the tested link; never claim an unrecorded hash was matched.

For new writes verify all four effective Public Access Block controls, no public
policy/ACL access, encryption at rest, bucket-owner-enforced ownership and
prefix-scoped PutObject/GetObject/metadata access. Verify the selected prefix's
lifecycle: one day for `deliveries/`; 90 days for `presentations/` without any
earlier overlapping expiration. Only retained decks require the presentation
infrastructure/image/profile gates. Never change infrastructure to pass them.
Check versioning and exact-key versions/delete markers before writing: unexpected
existing versions or versioning outside the approved retention policy block the
write. If versioning is enabled, approved bounded noncurrent-version expiry is
also required; current-object expiration alone is insufficient. Never overwrite.
Sensitive documents and submissions remain prohibited under both policies.

## Upload and tested link

1. Inspect the staged regular file and record bytes/SHA-256, comparing any
   download result. The selected profile caps transfer size at 104857600 bytes;
   decks additionally require positive size. Follow the transfer skill's
   one-deck-per-request, sequential shared-capacity guidance.
2. Obtain exact upload approval for artifact, bucket/key, profile and selected
   retention. Mint a PUT with `aws_aws___get_presigned_url`, `operation: upload`,
   verified region and `expires_in: 900`. Do not add `s3_params` requiring
   unsupported helper headers. Pass the unchanged URL to
   `agent-pipe_upload_artifact`; its exact permission prompt remains required.
3. Compare upload bytes and fresh staged-file inspection to the original
   identity. Use AWS `HeadObject` for ContentLength, encryption, LastModified,
   VersionId and safe metadata against the intended upload/versioning policy.
   ETag is not SHA-256. Do not return object bytes or credentials.
4. For uploads or existing-object delivery, mint a GET with `operation: download`
   and `expires_in: 900` for the exact key. Fully read it with
   `agent-pipe_verify_download` using the selected profile and unchanged URL.
   Compare bytes/SHA-256 to staged/recorded identity when available; any mismatch
   blocks delivery. Do not substitute HEAD, curl, fetch tools or URL rewriting.
5. Return the SAME tested URL as `[Download artifact](url)`, approximately
   15 minutes or less if signing credentials expire sooner. This is transient
   user output, not a saved URL. Never return PUT URLs.
6. Return/record only non-sensitive bucket/key/region, measured bytes, SHA-256,
   creation time and selected requested retention for new writes (1 for ordinary
   deliveries, 90 for presentations); include `request_id` only for SlideSpeak.
   Return the durable `s3://<bucket>/<key>` reference. For existing GETs do not
   invent/reset retention. Separate requested policy from applied evidence.
7. Only after verified storage and return of the durable reference may exact
   local cleanup be approved under `cloud-artifact-transfer`. Never auto-delete.

## Fresh links and failures

Fresh-link requests reuse the recorded bucket/key/region, recheck access and
metadata, and fully verify a new 900-second GET against recorded bytes/hash.
No regeneration, re-upload or retention reset. If a reference is missing, ask
for it rather than guessing. Report expired/missing/changed objects honestly.

Allow one fresh URL and one sequential retry for expiry/transient failures,
not unresolved permission, profile, hash or known capacity failures. After an
ambiguous PUT inspect the exact key first; if correct, verify without another
PUT. Unexpected versions block retry. Do not hand out untested S3 links.
If retained delivery is unavailable or declined, preserve the SlideSpeak
`request_id` and offer its tool-returned temporary GET link under the career
skill, explicitly NOT ARCHIVED; do not claim a persisted object. Generic S3
failures do not imply a SlideSpeak fallback. No public-storage/credential bypass.
Signed URLs are bearer capabilities; short expiry is not revocation and policy
or credential changes may invalidate them sooner.
