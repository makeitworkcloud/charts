# s3-presigned-file-delivery

Deliver a file from AWS S3 to the user as a clickable, time-limited download link using the `aws` MCP integration. Use when the user asks to download, share, or "get a link to" an S3 object, or to hand a session artifact to storage.

## Capability

`aws___get_presigned_url` (aws MCP, mcp-proxy-for-aws) mints signed GET (download) or PUT (upload) URLs. The bucket stays private; the link works for anyone holding it until it expires. Downloads succeed only for objects the signing role (`opencode-managed-mcp`) can read (`s3:GetObject`).

## Choosing the mode (verify, don't assume)

1. Read-only check first: `aws s3api get-public-access-block` / `get-bucket-policy`.
2. Public-by-policy buckets (e.g. `makeitwork.cloud`): direct permanent URL — no presign.
3. Private buckets (e.g. `mitw-bedrock-batch`): presigned GET, short TTL.
4. Never presign or link `mitw-tf-*-infra` state buckets — state files carry secrets. Inspect object sensitivity before sharing from any private bucket.

## Procedure

1. Mint with `expires_in: 900`. SigV4 caps at 7 days, but STS-signed URLs die with the MCP session's credentials — treat ~15 minutes as the practical max.
2. Present as a markdown link, state the expiry, offer to re-issue on demand.
3. Optional validation from this server: `timeout 30 wget -O - "<url>"` (busybox wget sends the URL verbatim; curl/node are absent).
4. For in-session reads, prefer `aws s3api get-object --bucket B --key K -`.

## Failure modes (verified 2026-09-02)

- Fetch tools return 400: they re-encoded the query string and broke SigV4. The link is valid for browsers/curl/wget — hand it to the user, don't re-fetch through URL-rewriting tools.
- 403 on download: the signing role lacks GetObject (minting itself always "succeeds" — signing is client-side math).
- HEAD fails against a GET-signed URL: the method is part of the signature.
- Links cannot be revoked before expiry; keep TTLs short.
