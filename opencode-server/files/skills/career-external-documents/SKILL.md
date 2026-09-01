---
name: career-external-documents
description: Use when generating presentation decks with SlideSpeak through the configured MCP service.
---

# Career external documents

Canonical text resumes and documents stay on the workspace pandoc pipeline (`make`, owner-run). Use SlideSpeak only for presentation decks the owner asks for.

## Service

- **SlideSpeak** (`slidespeak` MCP): presentation decks — interview or portfolio presentations. Never for text resumes or PDF documents. Canva and Plus AI are deferred because their hosted MCP integrations require interactive OAuth, which is unsuitable for this shared headless server.

## Generate

1. Confirm the owner wants a deck; any text resume or document request routes back to the workspace pipeline instead.
2. Create the presentation from the prepared content, then take the returned download link or presentation reference.
3. Deliver the link or exported-file reference to the owner as a markdown link — `[label](url)` — so it is clickable in the web client; presigned export URLs expire in minutes, so state the expiry and offer to re-issue on request. Record only metadata (date, service, artifact, link) in `work/YYYY-MM-DD-<topic>.md`; retain no submitted-application artifacts.

## Availability and authorization

- SlideSpeak authentication is provided by the cluster-owned MCP proxy. If a call reports an unavailable service, authentication failure, or plan limitation, stop and report it to the owner. Never retry-loop, initiate provider OAuth, or request or handle credentials.
- Do not substitute another external service when SlideSpeak reports a limitation.

## Data boundary

- SlideSpeak is a third-party AI processor. Send only the deck content the owner explicitly requested; never send `career-data.yaml`, tracker content, or whole documents wholesale unless the owner named that document for external generation.
- Secrets and credentials never go to any external service.
