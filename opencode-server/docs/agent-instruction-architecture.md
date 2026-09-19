# Agent instruction architecture

## Purpose

This document records why the chart packages a short shared `AGENTS.md` and places the complete operating policy directly in primary-agent definitions. It is design documentation, not runtime configuration; the canonical packaged prompts remain under [`files/`](../files/).

## Design

### Universal floor

[`files/AGENTS.md`](../files/AGENTS.md) is deliberately limited to rules that must constrain every runtime agent, including subagents:

- headless-server and no-workstation boundary;
- MCP-only execution when an owning MCP route exists;
- CI as the validation authority;
- no invented operational facts;
- secret, state, and sensitive-output protection; and
- explicit confirmation before destructive, publication, or live-system work.

This floor is intentionally short. It protects narrow delegated workers without forcing them to carry primary-agent procedures they cannot authorize or complete.

### Primary agents

[`files/agents/default.md`](../files/agents/default.md) is a full-capability, generic primary-agent definition and the example for new primary agents. It contains the complete primary operating policy directly in its own prompt.

Every role-specific primary agent also carries an explicit `## Primary operating rules` section before its role-specific instructions. The section is self-contained and covers GitHub identity and routing, Make IT Work Cloud repository discovery through the `codebase-memory` graph index for public repositories and owner-approved private repositories present in the read-only cache, proactive cost-aware subagent delegation and primary-decision boundaries, repository and cross-repository context passes, delivery-stage evidence, comment and bespoke-content preferences, direct-main agent-knowledge maintenance within an authorized own subtree, pull-request discipline, confirmation gates, and operational reporting.

Chart maintainers use `default.md` as the reference when maintaining these policies. Runtime agent files must remain self-contained and must not instruct agents to consult or align themselves with another agent file.

Primary agents prefer self-explanatory code and canonical documentation. A comment is retained or added only when it documents a non-obvious, durable rationale unavailable from them, such as an approved security, compatibility, standards, or ownership exception. They prefer vendor- or canonical-owner-maintained solutions; a new self-maintained artifact is a last resort that requires an alternatives assessment, clear producer-consumer and maintenance impact, and explicit owner approval before it is created.

The `agent-knowledge` exception is intentionally narrow: when the repository's current contract grants a named primary agent authority over its own `docs/agents/<agent>/` subtree, a verified, non-sensitive update is committed directly to `main` with a scoped descriptive commit. No branch, pull request, or merge operation is needed for that repository-local action. Pull requests remain available for owner-requested review and are required outside the agent's own subtree. The generic `default` agent has no autonomous knowledge subtree and must not use the exception until a human owner establishes one or grants explicit scoped authority. This exception does not waive owner confirmation required by a subset for new facts, nor the universal safety rules.

`default.md` is packaged and selectable, and [`files/opencode.json`](../files/opencode.json) selects `default` for unqualified sessions. Changing `default_agent` is a separate user-facing routing decision, not an incidental result of this instruction refactor.

### Subagents

Subagents receive the short universal floor plus their dedicated agent definition and the bounded task prompt supplied by the primary agent. They do not receive the full primary policy.

Primary agents proactively dispatch a subagent for bounded, independently verifiable research, extraction, review, or implementation whenever a capable lower-cost worker can reduce cost or latency. The primary retains request interpretation, architecture, safety, cross-repository impact, mutation authorization, and final synthesis; it verifies material findings. Independent scopes may run in parallel.

[`files/agents/terra.md`](../files/agents/terra.md) defines `terra`, a full-capability, generic execution subagent using `openai/gpt-5.6-terra` with the default variant. A primary may select it for bounded coding, debugging, or repository tasks when it needs execution capacity. It does not change the `default` primary-agent selection or delegate primary ownership; the assigning primary must supply authority, scope, safety constraints, and completion criteria in the task prompt.

[`files/agents/devops-engineer.md`](../files/agents/devops-engineer.md) defines a read-only DevOps integration and delivery reviewer using `openai/gpt-5.6-terra` with no `variant` override. It supports `DESIGN` mode for a supplied proposal and `CHANGE` mode for a completed diff and workflows. Both modes require the parent to provide intent, repository guidance, producer-consumer ownership and contracts, and validation evidence with gaps; missing essential evidence yields `HOLD`. The reviewer assesses maintained upstream actions and shared workflows, but does not treat JavaScript supplied to `actions/github-script` as upstream-maintained implementation.

Its integration map covers callers and callees; declared inputs, secret declarations, permissions, outputs, and checks; fork, bot, and merge-queue event conditions; downstream identity; artifact format, digest, and source; runner compatibility; false-green paths; concurrency, retries, and idempotence; generated ownership and GitOps handoffs; and observable failures. It can return `ADVANCE` only with no Critical or High findings and sufficient evidence for the current stage. Static consistency does not prove runtime behavior, and future pull-request CI is not a prerequisite to opening a pull request.

The reviewer has `edit` and `bash` denied and explicitly prohibits writes, pull-request changes, dispatches, reruns, merges, publication, provider fallback, live mutation, credential-value access, and `agent-knowledge` work. The primary remains responsible for architecture, cross-repository ownership, safety, and final authority. The reviewer routes deep security analysis to `infra-security-reviewer`.

The repository-capable `kimi` and `kimi-256k` subagents include a compact, self-contained `codebase-memory` and GitHub routing rule because they may perform bounded repository passes. Other subagents receive their authoritative sources, read/write authority, and routing requirements in the delegation prompt.

Specialized SDLC reviewer subagents extend the `recruiter-resume-reviewer` pattern to delivery work. `adversarial-code-reviewer`, `qa-engineer`, `release-engineer`, `infra-security-reviewer`, and `devops-engineer` are read-only (`edit` and `bash` denied), declare required inputs and return a hold or blocked verdict when one is absent, review in a fresh context independent of the authoring session, and emit a ranked-findings verdict the parent must resolve or explicitly waive before proceeding. `qa-engineer` owns the detailed test-coverage and documentation-adequacy assessment. `docs-writer` remains the read-only drafter for standalone documentation.

Code-touching primary agents (`default`, `makeitwork`, `xnoto`, `career`, and `teacher`) carry a pre-pull-request review gate in their primary policy. They dispatch `adversarial-code-reviewer` for non-trivial changes, add `infra-security-reviewer` for infrastructure-affecting changes, and dispatch `devops-engineer` for CI, workflow, shared-workflow, artifact, GitOps-handoff, runner, or delivery-integration contracts. They dispatch `qa-engineer`, `release-engineer`, or `docs-writer` conditionally for validation, release, or documentation risk. Lifestyle primaries do not carry this mandatory gate because they do not author code, chart, or workflow changes.

## Why direct definitions intentionally duplicate policy

OpenCode Markdown agent files define independent agent prompts; a file named `default.md` does not provide runtime inheritance to other agents. The chart also mounts every `files/agents/*.md` directly into the OpenCode configuration rather than composing prompt fragments.

A separate shared prompt fragment or generated frontmatter scheme would add a custom rendering contract without giving the agent a direct, role-local policy. Directly embedding the shared primary block therefore trades a small, explicit maintenance burden for stronger instruction salience, no unsupported inheritance assumption, visible role-specific exceptions, and a straightforward review surface.

## Maintenance rules

- Treat `default.md` as the maintainer reference when creating or materially changing a primary agent. Copy the applicable primary rules into that agent definition; do not replace them with a reference to `default.md`.
- When changing a shared primary rule, review every primary agent's primary-policy section in the same pull request. Preserve stricter role-specific rules.
- When changing a universal safety rule, update `AGENTS.md` rather than duplicating it across subagents.
- Keep subagent prompts limited to their execution mode and any routing they cannot safely infer from the bounded delegation prompt.
- Any change below `opencode-server/files/` is immutable chart content and requires a fresh `Chart.yaml` version. PR checks validate authored chart content; only an explicitly approved merge can publish it and start the separate GitOps version-pin flow.

## Review triggers

Revisit this design when OpenCode adds supported agent inheritance or prompt composition, when the chart's ConfigMap/mount strategy changes, when a new primary or repository-capable subagent is introduced, when agent-knowledge subtree authority changes, or when evidence shows that direct primary-agent instructions no longer improve instruction adherence.
