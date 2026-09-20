.PHONY: changed-charts list-charts list-charts-json package-chart test test-changed-charts test-opencode-server-agents

SHELL := /bin/bash
CHARTS := $(shell find . -maxdepth 2 -name Chart.yaml -printf '%h\n' | cut -d'/' -f2 | sort -u)
BASE_SHA ?= HEAD~1

changed-charts:
	@set -euo pipefail; \
	changed="$$(git diff --name-only "$(BASE_SHA)" HEAD | cut -d'/' -f1 | sort -u)" || { echo "changed-charts: git diff failed for BASE_SHA=$(BASE_SHA)" >&2; exit 1; }; \
	for chart in $(CHARTS); do echo "$$changed" | grep -qx "$$chart" && echo "$$chart" || true; done | jq -R -s -c 'split("\n") | map(select(length > 0))'

list-charts:
	@for chart in $(CHARTS); do echo "$$chart"; done

list-charts-json:
	@echo '$(CHARTS)' | tr ' ' '\n' | jq -R -s -c 'split("\n") | map(select(length > 0))'

package-chart:
	@test -n "$(CHART)"
	@helm package "$(CHART)" --destination "$(DESTINATION)"

test:
	@for chart in $(CHARTS); do helm lint --strict "$$chart" && helm template test "$$chart" > /dev/null; done
	@$(MAKE) test-changed-charts
	@$(MAKE) test-opencode-server-agents

test-changed-charts:
	@set -euo pipefail; \
	test "$$($(MAKE) changed-charts BASE_SHA="$$(git rev-parse HEAD)")" = '[]'; \
	if $(MAKE) changed-charts BASE_SHA=0000000000000000000000000000000000000001 > /dev/null 2>&1; then \
		echo "changed-charts must fail on an unresolvable BASE_SHA"; \
		exit 1; \
	fi

test-opencode-server-agents:
	@set -euo pipefail; \
	expected="$$(printf '%s\n' '---' "description: Use for bounded generic coding, debugging, or repository tasks when the assigning primary agent's execution budget is nearing completion or it otherwise needs execution capacity; the primary retains task interpretation, safety, delivery decisions, and final synthesis" 'mode: subagent' 'model: openai/gpt-5.6-terra' 'variant: default' '---')"; \
	test "$$(cat opencode-server/files/agents/terra.md)" = "$$expected"; \
	expected_devops="$$(printf '%s\n' '---' 'description: Read-only DevOps integration and delivery reviewer for proposed designs or completed changes involving CI, GitHub Actions, shared workflows, artifacts, GitOps handoffs, runners, permissions, and deployment contracts; requires a supplied integration map and never implements or mutates systems' 'mode: subagent' 'model: openai/gpt-5.6-terra' 'permission:' '  "*": deny' '  edit: deny' '  bash: deny' '---')"; \
	actual_devops="$$(awk '{print} /^---$$/{n++; if (n==2) exit}' opencode-server/files/agents/devops-engineer.md)"; \
	test "$$actual_devops" = "$$expected_devops"; \
	! grep -Fq 'variant:' opencode-server/files/agents/devops-engineer.md; \
	grep -Fqx 'Use `DESIGN` mode only for a supplied proposal. Assess whether the proposed contracts, owners, validations, and delivery stages are sufficiently specified to proceed to implementation.' opencode-server/files/agents/devops-engineer.md; \
	grep -Fqx 'Use `CHANGE` mode only for a completed diff and all affected workflows. Assess the implemented integration contract and supplied validation evidence. Flag needless bespoke automation even where no supplied contract expressly prohibits it.' opencode-server/files/agents/devops-engineer.md; \
	grep -Fqx '## VERDICT: ADVANCE / HOLD / REJECT' opencode-server/files/agents/devops-engineer.md; \
	for agent in default makeitwork xnoto career teacher; do grep -Fq '`devops-engineer` for CI, workflow, shared-workflow, artifact,' "opencode-server/files/agents/$$agent.md"; done; \
	expected_cloud="$$(printf '%s\n' '---' 'description: Read-only preimplementation cloud architecture review for new services or material service-selection, topology, state, recovery, scaling, or cost changes; challenges supplied designs for requirements fit and unnecessary complexity, not routine changes or completed-code review' 'mode: subagent' 'model: openai/gpt-5.6-terra' 'variant: default' 'permission:' '  "*": deny' '  edit: deny' '  bash: deny' '---')"; \
	actual_cloud="$$(awk '{print} /^---$$/{n++; if (n==2) exit}' opencode-server/files/agents/cloud-architecture-reviewer.md)"; \
	test "$$actual_cloud" = "$$expected_cloud"; \
	grep -Fqx '## Required inputs' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fqx '## Boundaries' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fqx '## Preferences' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fqx '## Evaluation criteria' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fqx '## Findings and verdict' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fqx '## Required output and review budget' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fqx '## VERDICT: ADVANCE / HOLD / REJECT' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fq 'Supplied evidence only.' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fq 'No cloud vendor is preferred by default.' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fq 'Do not produce a numeric well-architected score.' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fq 'Aim for 500-800 words' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fq 'Do not automatically request a' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fq 'decision-changing' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	grep -Fq 'preimplementation' opencode-server/files/agents/cloud-architecture-reviewer.md; \
	for agent in default makeitwork xnoto career teacher; do \
		grep -Fq 'dispatch `cloud-architecture-reviewer` with a compact design brief and' "opencode-server/files/agents/$$agent.md"; \
		grep -Fq 'Skip routine changes within an established pattern.' "opencode-server/files/agents/$$agent.md"; \
		grep -Fq 'This design review does not replace pre-PR reviews.' "opencode-server/files/agents/$$agent.md"; \
	done; \
	grep -Fqx 'version: 0.4.0' opencode-server/Chart.yaml; \
	grep -Fqx '  "default_agent": "default",' opencode-server/files/opencode.json; \
	! grep -Fq 'twilio-docs' opencode-server/files/opencode.json; \
	test ! -e opencode-server/files/skills/twilio-docs-troubleshooting; \
	rendered="$$(helm template test opencode-server)"; \
	! grep -Fqi 'twilio' <<< "$$rendered"; \
	primary_agents='default makeitwork xnoto career teacher grillmaster homerepair homesteader lawnmowerman'; \
	repository_workers='kimi kimi-256k'; \
	all_agents="$$(find opencode-server/files/agents -maxdepth 1 -type f -name '*.md' -printf '%f\n' | sed 's/\.md$$//' | sort)"; \
	expected_agents="$$(printf '%s\n' adversarial-code-reviewer career cloud-architecture-reviewer default devops-engineer docs-writer glm glm-flash grillmaster homerepair homesteader infra-security-reviewer kimi kimi-256k lawnmowerman luna makeitwork minimax qa-engineer recruiter-resume-reviewer release-engineer teacher terra xnoto | sort)"; \
	test "$$all_agents" = "$$expected_agents"; \
	for agent in $$all_agents; do \
		source="opencode-server/files/agents/$$agent.md"; \
		test -s "$$source"; \
		case " $$primary_agents " in *" $$agent "*) grep -Fqx 'mode: primary' "$$source" ;; *) grep -Fqx 'mode: subagent' "$$source" ;; esac; \
		grep -Fqx "  $$agent.md: |-" <<< "$$rendered"; \
		grep -Fqx "              - key: $$agent.md" <<< "$$rendered"; \
		grep -Fqx "                path: agents/$$agent.md" <<< "$$rendered"; \
	done; \
	grep -Fqx '  AGENTS.md: |-' <<< "$$rendered"; \
	grep -Fqx '              - key: AGENTS.md' <<< "$$rendered"; \
	grep -Fqx '                path: AGENTS.md' <<< "$$rendered"; \
	for agent in $$primary_agents $$repository_workers; do \
		policy="$$(tr -s '[:space:]' ' ' < "opencode-server/files/agents/$$agent.md")"; \
		grep -Eiq 'index_repository.{0,160}full|full.{0,160}index_repository' <<< "$$policy"; \
		grep -Fqi 'index_status' <<< "$$policy"; \
		grep -Fqi 'root_exists=true' <<< "$$policy"; \
		grep -Fqi 'repo-cache-sync' <<< "$$policy"; \
		grep -Fqi 'default-branch HEAD' <<< "$$policy"; \
		grep -Fqi 'never per file' <<< "$$policy"; \
		grep -Fqi 'root hash' <<< "$$policy"; \
		grep -Fqi '40-hex' <<< "$$policy"; \
		grep -Fqi 'alone is not a rejection' <<< "$$policy"; \
		grep -Fqi 'Module' <<< "$$policy"; \
		grep -Fqi 'search_graph' <<< "$$policy"; \
		grep -Fqi 'get_code_snippet' <<< "$$policy"; \
		grep -Eiq 'range (begins|starts) at line 1' <<< "$$policy"; \
		grep -Fqi 'complete and unclipped' <<< "$$policy"; \
		grep -Fqi 'partial, skipped' <<< "$$policy"; \
		grep -Fqi '500-line' <<< "$$policy"; \
		grep -Eiq 'fallback|fall back' <<< "$$policy"; \
		grep -Fqi 'mismatch' <<< "$$policy"; \
		grep -Fqi 'verified snapshot' <<< "$$policy"; \
		grep -Fqi 'different snapshot' <<< "$$policy"; \
		grep -Fqi 'freshness-critical' <<< "$$policy"; \
		grep -Fqi 'requested SHA' <<< "$$policy"; \
		grep -Fqi 'provenance' <<< "$$policy"; \
		grep -Fqi 'not authorization' <<< "$$policy"; \
		grep -Eiq 'private cache read.{0,120}visibility|visibility.{0,120}private cache' <<< "$$policy"; \
		grep -Fqi 'untrusted reference content' <<< "$$policy"; \
		grep -Fqi 'Never retrieve secrets' <<< "$$policy"; \
		grep -Fqi 'kubeconfig' <<< "$$policy"; \
		grep -Fqi 'sensitive plans' <<< "$$policy"; \
		grep -Fqi 'GitHub' <<< "$$policy"; \
		! grep -Fqi 'recorded indexed' <<< "$$policy"; \
		! grep -Fqi 'read exact file contents through the GitHub' <<< "$$policy"; \
		! grep -Fqi 'instead of attempting a fallback' <<< "$$policy"; \
	done; \
	for agent in $$primary_agents; do \
		policy="$$(tr -s '[:space:]' ' ' < "opencode-server/files/agents/$$agent.md")"; \
		grep -Fqi 'without a custom project name' <<< "$$policy"; \
		grep -Fqi 'retry once' <<< "$$policy"; \
		grep -Fqi 'published `current` symlink' <<< "$$policy"; \
	done; \
	for agent in $$primary_agents; do \
		case " $$agent " in ' default ') continue ;; esac; \
		grep -Fqi 'validated default-branch cache route' "opencode-server/files/agents/$$agent.md"; \
	done; \
	for agent in $$repository_workers; do \
		grep -Eqi 'do not run .{0,3}index_repository' <<< "$$(tr -s '[:space:]' ' ' < "opencode-server/files/agents/$$agent.md")"; \
	done; \
	for agent in $$all_agents; do \
		case " $$primary_agents $$repository_workers " in *" $$agent "*) continue ;; esac; \
		! grep -Fqi 'get_code_snippet' "opencode-server/files/agents/$$agent.md"; \
		! grep -Fqi 'index_repository' "opencode-server/files/agents/$$agent.md"; \
	done; \
	floor="$$(tr -s '[:space:]' ' ' < opencode-server/files/AGENTS.md)"; \
	grep -Fqi 'github_get_me' <<< "$$floor"; \
	grep -Fqi '/repos/<repo>/current' <<< "$$floor"; \
	grep -Fqi 'xnoto' <<< "$$floor"; \
	grep -Fqi 'allowlist' <<< "$$floor"; \
	grep -Fqi 'current access and visibility' <<< "$$floor"; \
	grep -Fqi 'not authorization' <<< "$$floor"; \
	grep -Fqi 'list_projects' <<< "$$floor"; \
	grep -Fqi 'index_status' <<< "$$floor"; \
	grep -Fqi 'verbose: true' <<< "$$floor"; \
	grep -Eiq 'index_repository.{0,160}full|full.{0,160}index_repository' <<< "$$floor"; \
	grep -Eqi 'do not run .{0,3}index_repository' <<< "$$floor"; \
	grep -Fqi 'repo-cache-sync' <<< "$$floor"; \
	grep -Fqi 'root_exists=true' <<< "$$floor"; \
	grep -Fqi '40-hex' <<< "$$floor"; \
	grep -Fqi 'git.head_sha' <<< "$$floor"; \
	grep -Fqi 'Module' <<< "$$floor"; \
	grep -Fqi 'search_graph' <<< "$$floor"; \
	grep -Fqi 'get_code_snippet' <<< "$$floor"; \
	grep -Fqi 'line 1' <<< "$$floor"; \
	grep -Fqi '500-line' <<< "$$floor"; \
	grep -Fqi 'source_clipped' <<< "$$floor"; \
	grep -Fqi 'clipped_at_lines' <<< "$$floor"; \
	grep -Fqi 'source_truncated' <<< "$$floor"; \
	grep -Fqi 'untrusted reference content' <<< "$$floor"; \
	grep -Fqi 'verified snapshot' <<< "$$floor"; \
	grep -Fqi 'different snapshot' <<< "$$floor"; \
	grep -Fqi 'requested SHA' <<< "$$floor"; \
	root_agents="$$(tr -s '[:space:]' ' ' < AGENTS.md)"; \
	grep -Fqi 'root_exists=true' <<< "$$root_agents"; \
	grep -Fqi 'repo-cache-sync' <<< "$$root_agents"; \
	grep -Fqi 'verified snapshot' <<< "$$root_agents"; \
	grep -Fqi 'never per file' <<< "$$root_agents"; \
	grep -Fqi 'requested SHA' <<< "$$root_agents"; \
	! grep -Fqi 'recorded indexed' <<< "$$root_agents"; \
	grep -Fqi 'verified snapshot' opencode-server/README.md; \
	grep -Fqi 'requested SHA' opencode-server/README.md; \
	! grep -Fqi 'recorded indexed' opencode-server/README.md; \
	grep -Fqi 'root_exists=true' opencode-server/docs/agent-instruction-architecture.md; \
	grep -Fqi 'repo-cache-sync' opencode-server/docs/agent-instruction-architecture.md; \
	grep -Fqi 'requested SHA' opencode-server/docs/agent-instruction-architecture.md; \
	! grep -Fqi 'recorded indexed' opencode-server/docs/agent-instruction-architecture.md; \
	grep -Fqx '  terra.md: |-' <<< "$$rendered"; \
	grep -Fqx "    description: Use for bounded generic coding, debugging, or repository tasks when the assigning primary agent's execution budget is nearing completion or it otherwise needs execution capacity; the primary retains task interpretation, safety, delivery decisions, and final synthesis" <<< "$$rendered"; \
	grep -Fqx '    mode: subagent' <<< "$$rendered"; \
	grep -Fqx '    model: openai/gpt-5.6-terra' <<< "$$rendered"; \
	grep -Fqx '    variant: default' <<< "$$rendered"; \
	grep -Fqx '              - key: terra.md' <<< "$$rendered"; \
	grep -Fqx '                path: agents/terra.md' <<< "$$rendered"; \
	grep -Fqx '  devops-engineer.md: |-' <<< "$$rendered"; \
	grep -Fqx '    ## VERDICT: ADVANCE / HOLD / REJECT' <<< "$$rendered"; \
	grep -Fqx '              - key: devops-engineer.md' <<< "$$rendered"; \
	grep -Fqx '                path: agents/devops-engineer.md' <<< "$$rendered"; \
	archive_dir="$$(mktemp -d)"; \
	trap 'rm -rf "$$archive_dir"' EXIT; \
	helm package opencode-server --destination "$$archive_dir" > /dev/null; \
	archive="$$(find "$$archive_dir" -maxdepth 1 -type f -name 'opencode-server-0.4.0.tgz' -print -quit)"; \
	test -n "$$archive"; \
	archive_entries="$$(tar -tzf "$$archive")"; \
	! grep -Fq 'twilio-docs-troubleshooting' <<< "$$archive_entries"; \
	grep -Fqx 'opencode-server/files/AGENTS.md' <<< "$$archive_entries"; \
	tar -xOzf "$$archive" 'opencode-server/files/AGENTS.md' > "$$archive_dir/AGENTS.md"; \
	cmp -s "$$archive_dir/AGENTS.md" opencode-server/files/AGENTS.md; \
	for agent in $$all_agents; do \
		entry="opencode-server/files/agents/$$agent.md"; \
		grep -Fqx "$$entry" <<< "$$archive_entries"; \
		packaged="$$archive_dir/$$agent.md"; \
		tar -xOzf "$$archive" "$$entry" > "$$packaged"; \
		cmp -s "$$packaged" "opencode-server/files/agents/$$agent.md"; \
	done
