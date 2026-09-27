---
name: career-external-documents
description: Use when generating presentation decks with SlideSpeak through the configured MCP service, including retained delivery and fresh links for user-directed non-sensitive decks.
---

# Career external documents

Use the existing SlideSpeak MCP only for decks the owner requests. Offer this
retained workflow for all user-directed non-sensitive decks, not just career
presentations. Text resumes/documents keep their existing document pipeline.
No new external service, workstation access or credential handling is granted.

## Generate once and select delivery

1. Confirm external-generation content and requested `response_format` before
   generation: `powerpoint` produces PPTX, `pdf` produces PDF. If omitted,
   verify the tool's documented default. Record the effective requested format
   with the returned `request_id`, not merely `task_id`. Never infer format
   from an untrusted URL/file extension or expand/parse bytes to guess it.
2. Generate once and poll within the tool contract. Offer approved private
   90-day retention and fresh tested 900-second S3 links on request. The owner
   may decline retention; it never waives exact download/upload/removal prompts.
3. For accepted retention load `cloud-artifact-transfer` and
   `s3-presigned-file-delivery`. Complete their retained-deck storage and
   deployed-helper gates; use the existing bucket/PVC only. Stage at most one
   deck per request, sequentially, within 100 MiB. The shared 1 GiB PVC has
   no reservation/quota: report uncertain capacity without guaranteeing space;
   stop on known insufficiency. ENOSPC fails/cleans the helper's partial
   temporary file; never blindly retry or evict another artifact.
4. Call `slidespeak_downloadPresentation(request_id)` for the existing deck.
   Before helper transfer, verify safe metadata: HTTPS, exact profile hostname,
   nonempty object path and required unique SigV4 fields. Preserve the URL
   signature; do not print it except for the explicit temporary-delivery case
   below. The [download docs](https://docs.slidespeak.co/v1/reference/download)
   show `slidespeak-files.s3.amazonaws.com` and refresh by `request_id`; verify
   actual responses rather than assume regional/path/signature shape. The only
   additional configured host is `slidespeak-files.s3.us-east-2.amazonaws.com`.
   A mismatch blocks helper transfer, not permission to expand the allowlist.
5. After exact download approval, use `slidespeak-exports` with normalized path
   `presentations/<session-id>/<artifact-id>/presentation.<ext>` under
   `/artifacts`. Use trusted session metadata or an explicitly labeled unique
   delivery token, never guess. Set `<ext>` to `pptx` for the verified
   `powerpoint` request, or `pdf` for the verified `pdf` request. Require positive
   size <=100 MiB; compare full download and inspection bytes/SHA-256.
6. After exact upload approval use `agent-presentations` and that same key in
   `agent-pipe`. Follow HeadObject and full S3 GET bytes/hash verification.
   Return the durable reference and same tested S3 link. Only afterward offer
   separately prompted local removal with the exact expected SHA-256.
7. Record only non-sensitive bucket/key/region, `request_id`, effective format,
   bytes, SHA-256, creation time and requested retention metadata in the
   authorized session record. Never persist signed URLs or submissions.
   Fresh retained links reuse S3 identity without generation.

## Temporary delivery and incomplete archives

If retention is unavailable or declined, preserve `request_id` and offer the
GET download URL returned by `slidespeak_downloadPresentation` for that exact
request as `[Download artifact](url)`. This explicit exception allows transient
vendor GET user output, NEVER PUT URLs or durable URL persistence. Require a
tool-produced HTTPS download URL, not an arbitrary supplied/page URL; do not
rewrite it or bypass authentication. Label it TEMPORARY, NOT ARCHIVED; the
provider's expiry is unspecified unless the tool reports it, so do not promise
900 seconds or another known TTL. Offer a fresh vendor link using the SAME
`request_id`, not regeneration. Do not claim helper verification if unavailable.
If an attempted archive failed, say archive INCOMPLETE; a vendor link or request
ID is not proof of S3 persistence. If the tool cannot return a usable download,
report that limitation. Refresh an expired URL once and retry once sequentially
within approved scope; no loop, new generation or automatic deletion.

## Availability and data boundary

Authentication remains in the cluster-owned SlideSpeak proxy. On service,
authentication or plan failure stop/report, never OAuth, request credentials,
retry-loop or substitute another service. Send only explicitly requested deck
content, never `career-data.yaml`, tracker content or whole documents wholesale
unless the owner named the document for external generation. Secrets, sensitive
documents and submissions remain excluded from retention; approval for generated
non-sensitive decks does not change those policies.
