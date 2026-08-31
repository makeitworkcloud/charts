---
name: career-external-documents
description: Use when generating designed PDF documents with Canva or presentation decks with Plus AI through the configured MCP services.
---

# Career external documents

Canonical text resumes stay on the workspace pandoc pipeline (`make`, owner-run). Use these services only for designed artifacts the owner asks for.

## Choose the service

- **Canva** (`canva` MCP): designed PDF documents — visual resume variants, designed cover letters, one-pagers, graphics.
- **Plus AI** (`plus-ai` MCP): presentation decks — interview or portfolio presentations. Never for text resumes.

## Generate

1. Confirm the artifact class matches the owner's request; if the request is a canonical text resume, route back to the workspace pipeline instead.
2. Canva: create the design from the prepared content, then export it as PDF. Plus AI: create the presentation from the prepared content (slide count, language, and template as applicable), then take the returned download link.
3. Deliver the download link or exported file reference to the owner. Record only metadata (date, service, artifact, link) in `work/YYYY-MM-DD-<topic>.md`; retain no submitted-application artifacts.

## Authorization

- These services use OAuth grants stored in the shared OpenCode home. If a call reports missing, expired, or insufficient authorization (for example a 401, an OAuth prompt, or a plan error), stop, name the provider, and ask the owner to complete or renew the OAuth flow in OpenCode. Never retry-loop and never attempt the OAuth flow yourself.
- Plus AI requires a paid Pro or Team plan; if the provider reports a plan limitation, report it rather than substituting another output.

## Data boundary

- These are third-party AI processors. Send only the document content the owner explicitly requested for the artifact; never send `career-data.yaml`, tracker content, or whole documents wholesale unless the owner named that document for external generation.
- Secrets and credentials never go to any external service.
