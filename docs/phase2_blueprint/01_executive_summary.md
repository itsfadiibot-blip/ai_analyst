# 01 — Executive Summary

## Purpose

This document is the **Phase 2+ architecture blueprint** for the `ai_analyst` Odoo 17 addon. It extends the confirmed-working Phase 1 platform into a **full autonomous analyst platform** with team workspaces, buying intelligence, safe write-actions, multi-model cost control, and enterprise-grade query safety.

## Phase 1 Baseline (Confirmed Working)

| Capability | Status |
|---|---|
| OWL Chat UI (client action) | Deployed |
| Allowlisted Tool Registry (11 tools) | Deployed |
| Read-only tools via `env.with_user(user)` | Enforced |
| JSON structured responses (answer, kpis, table, chart, actions, meta) | Deployed |
| CSV export | Deployed |
| Saved reports & dynamic dashboards | Deployed |
| Provider abstraction (Anthropic live, OpenAI skeleton) | Deployed |
| API keys from env vars | Deployed |
| Audit logging (tool calls + timings) | Deployed |
| Multi-company + ACL/record rules | Enforced |
| Rate limiting (20 req/min) | Enforced |
| Console mode toggle | Deployed (needs refinement) |

## Phase 2 — What Changes

| Area | Change |
|---|---|
| **Workspaces** | 4 team workspaces (Sales, Buying, POS, Customer Service) with role-scoped tool packs, dashboards, and prompt packs. Shared engine—zero duplication. |
| **Dimension Dictionary** | Dynamic, configurable product dimension registry (gender, age group, brand, category, season, color). Synonym/alias mappings. No hardcoded season logic. |
| **Big Query Safety** | Inline preview row limits, async export jobs with batching + progress + download, query cost estimation, tool-call budgets, caching layer. |
| **Buying Intelligence** | Velocity, sell-through, coverage, dead stock detection. Explainable results. CSV always. |
| **Safe Actions Framework** | Proposal → Approval → Execute pattern. Draft PO creation only. AI never directly mutates business records. Full execution logging. |
| **Model Routing** | Cheap-first with deterministic escalation. Validation gates. Cost budgets. Direct routing via `ai_gateway` (recommended over OpenRouter/LiteLLM). |
| **Security Hardening** | Prompt injection defense, data exfiltration prevention, ACL bypass protection, "data dump" guardrails. |
| **Performance** | read_group optimization, DB indexes, result caching, pre-aggregation tables, read replica routing. |

## Guiding Principles

1. **Extend, don't rewrite** — Phase 1 models, tools, and providers are preserved. New models and tools are additive.
2. **Allowlist-only** — No unrestricted ORM. No free-form SQL from the LLM. Every tool is registered, validated, and audited.
3. **User's permissions, always** — `env.with_user(user)` on every tool call. No `sudo()` in analytics paths.
4. **Proposal-gated writes** — AI can suggest actions. Humans approve. System executes. Full audit trail.
5. **Dynamic dimensions** — Seasons, brands, categories are data, not code. Configurable via UI.
6. **Cost-conscious** — Cheap models handle 80%+ of queries. Expensive models are reserved for ambiguity, complexity, or action proposals.
7. **Safety at scale** — Every query has row limits, timeouts, and cost estimation. Large exports run async with progress reporting.

## Delivery Phases

| Phase | Scope | Target |
|---|---|---|
| **Phase 2** | Workspaces, Dimension Dictionary, Big Query Safety, Model Routing, Security Hardening | Foundation |
| **Phase 3** | Buying Intelligence tools, Safe Actions Framework (draft POs), Performance optimization | Intelligence |
| **Phase 4** | Advanced automation, Finance/Inventory workspaces, Pre-aggregation, Read replicas | Scale |

## Key Non-Functional Requirements

- **Odoo 17 compatible** — Standard ORM patterns, no monkey-patching, no raw SQL from LLM
- **Multi-company** — Every new model carries `company_id` with record rules
- **Audit-complete** — Every AI query, tool call, export job, proposal, and approval is logged
- **Graceful degradation** — Provider failures fall back. Export failures are retryable. Cache misses hit live data.
