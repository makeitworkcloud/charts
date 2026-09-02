# s3-presigned-file-delivery

Deliver a file from AWS S3 to the user as a clickable, time-limited download link using the `aws` MCP integration. Use when the user asks to download, share, or "get a link to" an S3 object, or to hand a session artifact to storage.

## Default delivery bucket

Use the private `agent-pipe` bucket by default after its OpenTofu root has been applied and functional access has been verified. It is for short-lived, non-secret agent-to-user artifacts only — PDFs, reports, and other user-requested outputs — under the `deliveries/` prefix.

- Never use `agent-pipe` for OpenTofu state, credentials, decrypted SOPS values, kubeconfigs, logs containing sensitive data, or a submission archive.
- Public access is blocked; encryption at rest and bucket-owner-enforced ownership are required infrastructure controls.
- The managed MCP role may write only `deliveries/*`; preserve that boundary in object keys.
- S3 lifecycle expiration makes objects eligible for deletion one day after creation. A presigned URL is much shorter-lived and does not extend object retention.
- Use another bucket only when the user explicitly directs it. Never presign or link `mitw-tf-*-infra` state buckets.

## Capability

`aws___get_presigned_url` (aws MCP, mcp-proxy-for-aws) mints signed GET (download) or PUT (upload) URLs. The bucket stays private; the link works for anyone holding it until it expires. Downloads succeed only for objects the signing role (`opencode-managed-mcp`) can read (`s3:GetObject`).

## Preflight

1. Confirm the AWS account and target region through the AWS MCP; never infer either from a bucket name.
2. Verify `agent-pipe` exists and its Public Access Block has all four protections enabled. If the bucket or the managed-role permissions are absent, report the infrastructure gate; do not fall back to a public bucket.
3. Use a collision-resistant key such as `deliveries/<session-id>/<filename>`. Do not use a user name, application name, or sensitive data in an object key.
4. Inspect the source and object metadata for sensitivity before delivery. A presigned link can be shared by anyone holding it until it expires.

## Procedure

### In-session artifact already on the OpenCode PVC

1. Mint a PUT URL for `agent-pipe` and the chosen `deliveries/...` key with `expires_in: 900`.
2. Upload the generated file with a direct HTTP PUT; the AWS CLI MCP cannot read a local file path. For a server-generated artifact, use the session shell with the exact URL unmodified:

   ```sh
   wget --method=PUT --body-file="/home/opencode/<file>" -q -O /dev/null "<presigned-put-url>"
   ```

3. Verify with `aws s3api head-object --bucket agent-pipe --key <key>`; do not print object bytes in the conversation.
4. Mint a GET URL with `expires_in: 900` and return it as a Markdown download link. State that it expires in about 15 minutes and offer to re-issue it.

### Owner-local house resume

House resume targets must still render through the owner-local `make` pipeline. The server cannot read the owner's workstation. Mint a one-time PUT URL for the same `agent-pipe` key, provide the owner a direct HTTP-upload command, then issue the GET link after the owner confirms the upload or the agent verifies the object exists. This transient delivery step does not change the career workspace rule that submitted-application artifacts are not retained.

## Failure modes

- Fetch tools return 400: they re-encoded the query string and broke SigV4. The link is valid for browsers/curl/wget — hand it to the user, don't re-fetch through URL-rewriting tools.
- 403 on upload or download: the signing role lacks the corresponding object permission, even though URL signing itself may succeed.
- HEAD fails against a GET-signed URL: the method is part of the signature.
- Links cannot be revoked before expiry; keep TTLs short.
- S3 lifecycle deletion is asynchronous after the one-day eligibility point; never treat it as an immediate purge mechanism.
