---
name: career-external-documents
description: Use when generating presentation decks with Plus AI through the configured MCP service.
---

# Career external documents

Canonical text resumes and documents stay on the workspace pandoc pipeline (`make`, owner-run). Use Plus AI only for presentation decks the owner asks for.

## Service

- **Plus AI** (`plus-ai` MCP): presentation decks — interview or portfolio presentations. Never for text resumes or PDF documents. (Canva was evaluated and deprecated 2026-08-31: its MCP offers only interactive OAuth, with no API auth flow usable on the shared headless server.)

## Generate

1. Confirm the owner wants a deck; any text resume or document request routes back to the workspace pipeline instead.
2. Create the presentation from the prepared content (slide count, language, and template as applicable), then take the returned download link.
3. Deliver the download link to the owner. Record only metadata (date, service, artifact, link) in `work/YYYY-MM-DD-<topic>.md`; retain no submitted-application artifacts.

## Authorization

- Plus AI uses an OAuth grant stored in the shared OpenCode home. If a call reports missing, expired, or insufficient authorization (for example a 401, an OAuth prompt, or a plan error), stop and ask the owner to complete or renew the OAuth flow in OpenCode. Never retry-loop and never attempt the OAuth flow yourself.
- Plus AI requires a paid Pro or Team plan; if the provider reports a plan limitation, report it rather than substituting another output.

## Data boundary

- Plus AI is a third-party AI processor. Send only the deck content the owner explicitly requested; never send `career-data.yaml`, tracker content, or whole documents wholesale unless the owner named that document for external generation.
- Secrets and credentials never go to any external service.
