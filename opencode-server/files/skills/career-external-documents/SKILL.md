---
name: career-external-documents
description: Use when generating presentation decks with Plus AI through the configured MCP service.
---

# Career external documents

Canonical text resumes stay on the workspace pandoc pipeline (`make`, owner-run). Use Plus AI only for presentation decks the owner asks for; it is not a replacement for canonical text resumes.

## Generate a presentation deck

1. Confirm the owner's request is for an interview or portfolio presentation, rather than a canonical text resume.
2. Use the `plus-ai` MCP to create the presentation from prepared content, including the requested slide count, language, and template when applicable. Take the returned download link.
3. Deliver the download link or exported-file reference to the owner. Record only metadata (date, service, artifact, link) in `work/YYYY-MM-DD-<topic>.md`; retain no submitted-application artifacts.

## Availability and authorization

- Plus AI availability is controlled by the configured cluster integration. If it reports unavailable, missing authorization, or an insufficient plan, stop, name Plus AI, and report the limitation to the owner. Never retry-loop, initiate a provider OAuth flow, or request or handle credentials.
- Plus AI requires a paid Pro or Team plan. Do not substitute another external service when the provider reports a plan limitation.

## Data boundary

- Plus AI is a third-party AI processor. Send only the document content the owner explicitly requested for the presentation; never send `career-data.yaml`, tracker content, or whole documents wholesale unless the owner named that document for external generation.
- Secrets and credentials never go to any external service.
