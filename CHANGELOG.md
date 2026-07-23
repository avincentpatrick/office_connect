# Changelog

All notable, user-visible changes to Office-Connect. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions align to **phase
completions** (e.g. `0.1.0` = Phase 0 complete) and match the `APP_VERSION`
constant in `office_connect/__init__.py`.

`[Unreleased]` accrues session by session and is promoted to a version at each
phase QA gate (see `docs/standards/development-workflow.md` §6) — this is what
makes the push-per-phase rule auditable.

## [Unreleased]

### Added
- **Master Plan v1** (2026-07-23, `docs/master-plan.md`): authoritative
  consolidation of the reference execution plan + its amending documents +
  two deep-research rounds (18 digests, `docs/research/`) + owner scope
  additions. Build sequence restructured into Stages A–I + Wave 2; binding
  connectedness contract (one shared core workflow engine for every approval
  flow; core-services registry; connection matrix; Rule 10 "shared service
  first"); consolidated statutory-deadline calendar; reference-corrections
  ledger (EO 77 3-cluster travel rates, FOI 15+20-working-day clock, GAM form
  numbering, RA 12009 procurement forms, ₱50k property threshold, and more).
- **Four new planned modules** (owner additions): QMS (controlled documents ·
  risk registry · management review), Supply Management, Planning & Budget
  (WFP/BED/BAR + PPMP/APP), Performance & Deliverables (SPMS · accomplishment
  reports · COA findings) — plus the Calendar of Activities as a connected
  core surface. Module docs scaffolded with government-standard scope.

### Changed
- **DMWIS renamed to DTWIS (Document Tracking & Workflow IS)** to distinguish
  document *tracking* from the new controlled-document *management* module;
  prefix registry updated (`dtwis_`), no schema existed yet.
- Foundation Increment 2 revised (explicit-step migrations replace
  migration-on-boot for production; 3-2-1 backup placement; git remote must
  live off the future production hardware); Increment 4 (spine amendments)
  added. Production substrate corrected to Hyper-V Ubuntu VM + Docker Engine
  in `tech-stack.md`.
- Development standards codified (2026-07-22): database naming / audit /
  soft-delete standards, UI token & component standards, tech-stack register,
  session workflow with next-session prompts, per-module documentation set,
  `CLAUDE.md` session contract.
- Phase 0 Increment 1 (2026-07-22): core schema spine (`core_tenant_configs`,
  `core_feature_flags`, `core_audit_logs`, `core_query_logs`,
  `core_activities`) via a single Alembic chain; automatic hash-chained audit
  trail on every data change; soft deletes with a global filter; least-
  privilege runtime DB role (`oc_app`, no DELETE anywhere);
  `GET /api/v1/config` (tenant + branding + feature flags, Redis-cached,
  fail-safe OFF, never 500); 31 QA-gate tests + import-linter contracts.
  Hardened by a 34-agent adversarial review (23 confirmed findings fixed).
- Feature-flag rollout note: flags default **OFF**; cohort widenings will be
  recorded here per release.
