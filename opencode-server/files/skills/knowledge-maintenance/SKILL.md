---
name: knowledge-maintenance
description: Use when completing work that establishes durable repository, ownership, delivery-chain, operational, or troubleshooting knowledge that may need a proactive agent-knowledge update.
---

# Proactive knowledge maintenance

Treat `makeitworkcloud/agent-knowledge` as durable operational memory, not a task log. Run this workflow after work establishes reusable facts and before finalizing the response.

## 1. Decide whether a write is warranted

Write only when current evidence adds or corrects a durable fact about repository lifecycle, ownership, generated files, producer-consumer relationships, release or GitOps delivery stages, reusable operations, or a recurring troubleshooting conclusion.

Do not write unverified assumptions, duplicated mutable configuration, transient incident narration, secrets, credentials, decrypted values, state, kubeconfigs, sensitive plans, raw runtime payloads, or personal data outside the owning subset's data policy.

## 2. Establish authority and evidence

1. Read `agent-knowledge`'s root contract, index, and your `docs/agents/<name>/README.md`.
2. Verify the proposed fact against current canonical repository guidance, source, checks, releases, or timestamped read-only live evidence.
3. Record source paths or URLs, immutable revisions where available, observation date, evidence stage, and uncertainty or invalidation conditions.
4. Write only in your own subtree. If the appropriate document is repo-wide or belongs to another agent, do not edit it; report the exact blocker.

## 3. Write and report

Keep a concise, descriptive Markdown record. Update or explicitly supersede stale documents instead of creating conflicting copies. Follow the current repository workflow for a direct `main` commit or pull request and inspect the content for prohibited material before publishing.

Before the final response, report exactly one:

- `Knowledge updated:` path and commit or pull request;
- `Knowledge not updated:` specific reason; or
- `Knowledge update proposed but blocked:` specific authority or evidence gap.
