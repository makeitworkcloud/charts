# OpenCode SMS bridge chart

This chart deploys the portable, single-replica `opencode-sms-bridge` Pod: a public signed-webhook ingress container and a private queue worker container. It is not a Twilio-account or cluster-integration chart.

## Ownership

The chart owns a Deployment and non-secret ConfigMap. `makeitworkcloud/kustomize-cluster` owns the existing `opencode` namespace, RWO state PVC, stable ClusterIP Service, public workload `TunnelBinding`, and all SOPS-encrypted Secret values. Do not define those resources here.

The Pod uses `Recreate` because the SQLite queue/session store is intentionally single-writer on an RWO PVC. It is annotated with the installed Reloader's named-Secret annotation so rotation of any referenced bridge or OpenCode Basic-auth Secret replaces both containers.

## Prerequisites

The GitOps consumer must provide these Secrets in the `opencode` namespace:

- `opencode-sms-bridge-routing` with `routing.json`, containing the Twilio account identifier, initial approved sender set, and exactly four fixed destination-to-`*-sms` agent mappings;
- `opencode-sms-bridge-shared` with the webhook-validation token, Fernet state-encryption key, and independent sender-HMAC key;
- `opencode-sms-bridge-worker` with a least-privilege Twilio API Key SID/secret for outbound replies; and
- the existing `opencode-server-auth` Secret for the worker's private OpenCode HTTP request.

Use an immutable published image SHA in `image.tag`; `latest` is only the source-chart default and must never be selected by the GitOps consumer.

## Image and audio gates

Image parts are disabled by default. Enable `config.imagePartsEnabled` only after the selected OpenCode model and deployed file-part API are functionally verified. Keep `config.whisperUrl` empty until a local Whisper-compatible service, capacity, and retention boundary are selected; audio MMS then receives a bounded non-processing reply rather than unvalidated forwarding.

## Rendered resource

- Deployment, sync wave `2`, with two hardened containers and a `Recreate` strategy.

The corresponding cluster overlay must place state, Secrets, and Service in wave `1`; the `TunnelBinding` belongs in wave `3`. These waves order only resources within the existing `opencode` child Application.
