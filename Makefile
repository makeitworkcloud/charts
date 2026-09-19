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
	grep -Fqx 'version: 0.3.0' opencode-server/Chart.yaml; \
	grep -Fqx '  "default_agent": "default",' opencode-server/files/opencode.json; \
	! grep -Fq 'twilio-docs' opencode-server/files/opencode.json; \
	test ! -e opencode-server/files/skills/twilio-docs-troubleshooting; \
	rendered="$$(helm template test opencode-server)"; \
	! grep -Fqi 'twilio' <<< "$$rendered"; \
	primary_agents='default makeitwork xnoto career teacher grillmaster homerepair homesteader lawnmowerman'; \
	all_agents="$$primary_agents kimi kimi-256k"; \
	for agent in $$all_agents; do \
		source="opencode-server/files/agents/$$agent.md"; \
		test -s "$$source"; \
		case " $$primary_agents " in *" $$agent "*) grep -Fqx 'mode: primary' "$$source" ;; *) grep -Fqx 'mode: subagent' "$$source" ;; esac; \
		policy="$$(tr '\n' ' ' < "$$source")"; \
		grep -Eiq 'index_repository.{0,160}full|full.{0,160}index_repository' <<< "$$policy"; \
		grep -Fqi 'index_status' <<< "$$policy"; \
		grep -Eiq 'indexed (revision|commit).{0,40}(sha|SHA)|sha.{0,40}indexed' <<< "$$policy"; \
		grep -Fqi 'Module' <<< "$$policy"; \
		grep -Fqi 'search_graph' <<< "$$policy"; \
		grep -Fqi 'get_code_snippet' <<< "$$policy"; \
		grep -Eiq 'range (begins|starts) at line 1' <<< "$$policy"; \
		grep -Eiq 'complete and unclipped' <<< "$$policy"; \
		grep -Eiq 'fallback|fall back' <<< "$$policy"; \
		grep -Fqi 'GitHub' <<< "$$policy"; \
		grep -Eiq 'private cache read.{0,120}visibility|visibility.{0,120}private cache' <<< "$$policy"; \
		grep -Fqi 'untrusted reference content' <<< "$$policy"; \
		grep -Fqi 'Never retrieve secrets' <<< "$$policy"; \
		grep -Fqi 'kubeconfig' <<< "$$policy"; \
		grep -Fqi 'sensitive plans' <<< "$$policy"; \
		! grep -Fqi 'read exact file contents through the GitHub' <<< "$$policy"; \
		grep -Fqx "  $$agent.md: |-" <<< "$$rendered"; \
		grep -Fqx "              - key: $$agent.md" <<< "$$rendered"; \
		grep -Fqx "                path: agents/$$agent.md" <<< "$$rendered"; \
	done; \
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
	archive="$$(find "$$archive_dir" -maxdepth 1 -type f -name 'opencode-server-0.3.0.tgz' -print -quit)"; \
	test -n "$$archive"; \
	archive_entries="$$(tar -tzf "$$archive")"; \
	! grep -Fq 'twilio-docs-troubleshooting' <<< "$$archive_entries"; \
	archive_agents="$$all_agents terra devops-engineer"; \
	for agent in $$archive_agents; do \
		source="opencode-server/files/agents/$$agent.md"; \
		entry="opencode-server/files/agents/$$agent.md"; \
		grep -Fqx "$$entry" <<< "$$archive_entries"; \
		packaged="$$archive_dir/$$agent.md"; \
		tar -xOzf "$$archive" "$$entry" > "$$packaged"; \
		cmp -s "$$packaged" "$$source"; \
	done
