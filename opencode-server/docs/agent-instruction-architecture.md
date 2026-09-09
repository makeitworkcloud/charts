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
self-contained and covers GitHub identity and routing, Make IT Work Cloud
repository discovery through the `codebase-memory` graph index for public
repositories and owner-approved private repositories present in the read-only
cache, proactive cost-aware subagent delegation and primary-decision boundaries,
repository and cross-repository context passes, delivery-stage evidence, direct-main
agent-knowledge maintenance within an authorized own subtree, pull-request
discipline, confirmation gates, and operational reporting.

Chart maintainers use `default.md` as the reference when maintaining these
policies. Runtime agent files must remain self-contained and must not instruct
agents to consult or align themselves with another agent file.

The `agent-knowledge` exception is intentionally narrow: when the repository's
current contract grants a named primary agent authority over its own
`docs/agents/<agent>/` subtree, a verified, non-sensitive update is committed
directly to `main` with a scoped descriptive commit. No branch, pull request,
or merge operation is needed for that repository-local action. Pull requests
remain available for owner-requested review and are required outside the
agent's own subtree. The generic `default` agent has no autonomous knowledge
subtree and must not use the exception until a human owner establishes one or
grants explicit scoped authority. This exception does not waive owner
confirmation required by a subset for new facts, nor the universal safety
rules.

### Subagents

Subagents receive the short universal floor plus their dedicated agent
definition and the bounded task prompt supplied by the primary agent. They do
not receive the full primary policy.

Primary agents proactively dispatch a subagent for bounded, independently
verifiable research, extraction, review, or implementation whenever a capable
lower-cost worker can reduce cost or latency. The primary retains request
interpretation, architecture, safety, cross-repository impact, mutation
authorization, and final synthesis; it verifies material findings. Independent
scopes may run in parallel.

The repository-capable `kimi` and `kimi-256k` subagents include a compact,
self-contained `codebase-memory` and GitHub routing rule because they may
perform bounded repository passes. Other subagents receive their authoritative sources,
read/write authority, and routing requirements in the delegation prompt.

Specialized SDLC reviewer subagents extend the `recruiter-resume-reviewer`
pattern to delivery work. `adversarial-code-reviewer`, `qa-engineer`,
`release-engineer`, and `infra-security-reviewer` are read-only (`edit` and
`bash` denied), declare required inputs and return `HOLD` or `BLOCKED` when one
is absent, review in a fresh context independent of the authoring session, and
emit a ranked-findings verdict the parent must resolve or explicitly waive
before proceeding.

`pr-approver` is a separate, read-only post-pull-request aggregate gate. After
all relevant checks reach terminal status, it verifies the exact head SHA,
prior-review disposition, necessary comments and exceptions, explicit user
approval for new bespoke maintained content, and test/documentation adequacy.
It is the final subagent before the parent requests explicit owner confirmation.
Its `PASS` is not a GitHub approval, merge authority, or a substitute for owner
confirmation; any later head, check, waiver, or delivery-evidence change
requires repeating it as the final gate.

`docs-writer` applies the same discipline to standalone repository
documentation: read-only, required inputs with a `BLOCKED` result when absent,
and every technical claim grounded in parent-supplied source, with ungrounded
claims flagged as UNVERIFIED rather than invented. It returns complete
ready-to-commit file contents and the parent performs the commit. It does not
write `agent-knowledge` subtrees — those remain primary-owned — and does not
draft agent instruction, policy, or skill files.

Code-touching primary agents (`default`, `makeitwork`, `xnoto`, `career`, and
`teacher`) carry a pre-pull-request review gate in their primary policy:
non-trivial changes are dispatched to the adversarial reviewer — with the
infrastructure-security reviewer for infrastructure-affecting changes — before
the pull request is opened, and `qa-engineer`, `release-engineer`, or
`docs-writer` are dispatched conditionally for validation, release, or
documentation risk. The lifestyle primaries (`grillmaster`, `homerepair`,
`homesteader`, `lawnmowerman`) intentionally do not carry the pre-pull-request
gate because they do not author code, chart, or workflow changes; they still
reach these subagents discretionally through description-based routing. Every
primary carries the `pr-approver` final-gate policy for any pull request it
creates; no primary may treat the gate as merge authority.

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
- When changing the direct-main knowledge exception, verify the current
  `agent-knowledge` authority for each affected named agent. Preserve any
  owner-confirmation requirements for facts and keep the generic `default`
  agent read-only unless its authority changes.
- When changing a universal safety rule, update `AGENTS.md` rather than
  duplicating it across subagents.
- Keep subagent prompts limited to their execution mode and any routing they
  cannot safely infer from the bounded delegation prompt. For `pr-approver`,
  preserve the exact-head and terminal-check requirements, final-subagent
  ordering, explicit approval requirement for bespoke content, and separate
  owner-confirmation gate.
- Any change below `opencode-server/files/` is immutable chart content and
  requires a fresh `Chart.yaml` version. PR checks validate authored chart
  content; only an explicitly approved merge can publish it and start the
  separate GitOps version-pin flow.

## Review triggers

Revisit this design when OpenCode adds supported agent inheritance or prompt
composition, when the chart's ConfigMap/mount strategy changes, when a new
primary or repository-capable subagent is introduced, when agent-knowledge
subtree authority changes, or when evidence shows that direct primary-agent
instructions no longer improve instruction adherence.
