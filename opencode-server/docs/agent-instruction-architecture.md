# Agent instruction architecture

## Purpose

This document records why the chart packages a short shared `AGENTS.md` and
places the complete operating policy directly in primary-agent definitions.
It is design documentation, not runtime configuration; the canonical packaged
prompts remain under [`files/`](../files/).

## Design

### Universal floor

[`files/AGENTS.md`](../files/AGENTS.md) is deliberately limited to rules that
must constrain every runtime agent, including subagents:

- headless-server and no-workstation boundary;
- MCP-only execution when an owning MCP route exists;
- CI as the validation authority;
- no invented operational facts;
- secret, state, and sensitive-output protection; and
- explicit confirmation before destructive, publication, or live-system work.

This floor is intentionally short. It protects narrow delegated workers without
forcing them to carry primary-agent procedures they cannot authorize or
complete.

### Primary agents

[`files/agents/default.md`](../files/agents/default.md) is a full-capability,
generic primary-agent definition and the example for new primary agents. It
contains the complete primary operating policy directly in its own prompt.

Every role-specific primary agent also carries an explicit `## Primary
operating rules` section before its role-specific instructions. The section is
self-contained and covers GitHub identity and routing, public Make IT Work
Cloud repository discovery through `repo-search`, proactive cost-aware
subagent delegation and primary-decision boundaries, repository and
cross-repository context passes, delivery-stage evidence, pull-request
discipline, confirmation gates, and operational reporting.

Chart maintainers use `default.md` as the reference when maintaining these
policies. Runtime agent files must remain self-contained and must not instruct
agents to consult or align themselves with another agent file.

Role-specific instructions follow the shared primary block and may impose
stricter requirements. For example, the homesteader agent remains restricted
to explicitly owner-authorized writes after confidential repository verification.
The stricter rule wins.

`default.md` is packaged and selectable, and [`files/opencode.json`](../files/opencode.json)
selects `default` for unqualified sessions. Changing `default_agent` is a
separate user-facing routing decision, not an incidental result of this
instruction refactor.

### Subagents

Subagents receive the short universal floor plus their dedicated agent
definition and the bounded task prompt supplied by the primary agent. They do
not receive the full primary policy.

Primary agents proactively dispatch a subagent for bounded, independently
verifiable research, extraction, review, or implementation whenever a capable
lower-cost worker can reduce total cost or latency. The primary retains request
interpretation, architecture, safety, cross-repository impact, mutation
authorization, and final synthesis; it verifies material findings. Independent
scopes may run in parallel.

The repository-capable `kimi` and `kimi-256k` subagents include a compact,
self-contained `repo-search` and GitHub routing rule because they may perform
bounded repository passes. Other subagents receive their authoritative sources,
read/write authority, and routing requirements in the delegation prompt.

## Why direct definitions intentionally duplicate policy

OpenCode Markdown agent files define independent agent prompts; a file named
`default.md` does not provide runtime inheritance to other agents. The chart
also mounts every `files/agents/*.md` directly into the OpenCode configuration
rather than composing prompt fragments.

A separate shared prompt fragment or generated frontmatter scheme would add a
custom rendering contract without giving the agent a direct, role-local policy.
Directly embedding the shared primary block therefore trades a small, explicit
maintenance burden for:

1. stronger practical instruction salience for each primary agent;
2. a concise global prompt for context-constrained subagents;
3. no unsupported inheritance assumption or custom prompt-generation layer;
4. visible role-specific exceptions adjacent to the policy they constrain; and
5. a straightforward review surface in ordinary Markdown diffs.

## Maintenance rules

- Treat `default.md` as the maintainer reference when creating or materially
  changing a primary agent. Copy the applicable primary rules into that agent
  definition; do not replace them with a reference to `default.md`.
- When changing a shared primary rule, review every primary agent's
  primary-policy section in the same pull request. Preserve stricter
  role-specific rules.
- When changing a universal safety rule, update `AGENTS.md` rather than
  duplicating it across subagents.
- Keep subagent prompts limited to their execution mode and any routing they
  cannot safely infer from the bounded delegation prompt.
- Any change below `opencode-server/files/` is immutable chart content and
  requires a fresh `Chart.yaml` version. PR checks validate authored chart
  content; only an explicitly approved merge can publish it and start the
  separate GitOps version-pin flow.

## Review triggers

Revisit this design when OpenCode adds supported agent inheritance or prompt
composition, when the chart's ConfigMap/mount strategy changes, when a new
primary or repository-capable subagent is introduced, or when evidence shows
that direct primary-agent instructions no longer improve instruction adherence.
