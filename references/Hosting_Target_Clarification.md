# Office-Connect — Hosting Target Clarification

**Companion to:** `OfficeConnect_Build_Execution_Plan_v1_0.docx` (v1.0, the single source of truth) and `Source_Grounding_and_Understanding.md`
**Status:** Author clarification (2026-07-22). Overrides the *production hosting target* of locked decision **C-4** for Office-Connect; leaves every other locked decision untouched.
**Purpose:** Record that Office-Connect will be self-hosted on an on-premise **Windows Server**, not on a Hugging Face Docker Space, and state what that changes — and, deliberately, what it does *not* change yet.

---

## 1. The clarification (binding)

| # | Fact | Status |
|---|---|---|
| 1 | **CSS-IS (Module 1) remains hosted on Hugging Face.** It is the live production survey app; it keeps running on HF and is migrated onto the platform per the plan's dual-migration model (Finding C-2). | Unchanged from plan |
| 2 | **Office-Connect (the platform) will be hosted on an on-premise Windows Server**, owned/operated by the bureau — **not** on a Hugging Face Space. | **Overrides C-4** for the platform |
| 3 | **The hosting/deployment work is handled *after* complete development.** During the build, the target is a local Windows development environment; production Windows Server provisioning is a deployment-phase activity, not a Phase-0 blocker. | New sequencing note |

The plan's locked decision **C-4** ("The whole platform runs on Hugging Face Spaces … the free Space tier (16 GB RAM, 2 vCPU)") is therefore **superseded for Office-Connect's own hosting**. Because C-4 is folded into Part III (Architecture) and Part V (Phases 0, 1, 7–8), those sections' *hosting mechanics* (not their build logic) are re-read through this note until the `.docx` is formally amended.

---

## 2. What this changes (deployment-time, resolve after development)

The plan's HF-specific apparatus maps onto Windows-Server equivalents. **None of these block development;** they are the deployment checklist for when the app is complete.

| Plan (HF Docker Space) | Windows Server equivalent | Note |
|---|---|---|
| Single Docker Space, HF provides public URL + HTTPS | Windows Server host; TLS via a reverse proxy (**IIS / nginx / Caddy**) in front of Uvicorn | HF "edge" no longer exists — the server owns HTTPS, routing, compression |
| Postgres on HF **persistent-storage add-on** (ephemeral 50 GB disk warning) | PostgreSQL installed as a **Windows service**, data dir on a real server volume | The whole "never put the DB on the ephemeral disk" hazard **disappears** — server disk is durable |
| Redis + Celery **in one container**, supervised by a process manager | Redis-for-Windows (**Memurai**) + Celery workers, each a **Windows service** (NSSM / built-in) | No single-container process manager; services are supervised by Windows |
| Keep-alive ping to prevent Space cold-start | Not needed — a Windows service is **always on** | Removes the keep-alive workflow entirely |
| Backups to a private **HF Dataset** | Scheduled `pg_dump` to server storage + off-box copy (network share / Google Drive / cloud) | Retention target (30 daily + 12 monthly) carries over; the *destination* changes |
| Document files in Google Shared Drive | May stay in Google Drive, **or** move to a server share — an open deployment choice | Either works; decide at deployment |
| Free-tier 2-vCPU concurrency load test (Phase 10) | Load test against the **actual Windows Server spec** instead | The "does one free Space hold ~40 users" question is replaced by the real server's capacity |
| US-hosted-data governance gate (Section 24 #6) | **On-prem hosting likely *eases* this** (data stays on bureau/DOH infrastructure) | Confirm with DOH; self-hosting is generally the more defensible posture |

**Docker's role is now optional.** The plan leaned on Docker because HF *required* a Docker Space. With a native Windows Server target, the app can be deployed as native Windows services. Docker (Desktop/Engine) remains a legitimate *reproducibility* choice for both dev and prod, but it is no longer architecturally mandatory.

---

## 3. What this does NOT change (still governed by the plan)

- The **application architecture**: FastAPI + PostgreSQL + Redis + Celery + React/Vite/Tailwind, single repo, table-prefixed single database, module-boundary import linter (Q11). All intact.
- The **11-phase build sequence** (Phase 0 → 10), the reimbursement-first vertical, and every functional spec.
- The **CSS-IS migration** (SQLite→Postgres, Jinja2→React), auth promotion to core, unified login, timezone handling (C-1) — all unchanged; CSS-IS still lives on HF and is migrated onto the platform as specified.
- The **data-spine / integration blueprint**, report factory, and module specs.

Only the *platform's production hosting substrate* moves from HF to Windows Server, and that move is scheduled **after** development.

---

## 4. Impact on the development environment (the near-term consequence)

Because production is now native Windows, **the local dev environment is built native-Windows-first**, which makes dev mirror prod:

- Python 3.12+, PostgreSQL, Redis (Memurai), Node, Tesseract installed on Windows directly.
- Dev service ports chosen to **not collide** with the existing Laragon `dev_pims` stack (Apache 80/443, MySQL 3306, `php artisan serve` on 8000, Vite 5173) — see the environment setup delivered alongside this note.
- Docker optional; used only if container reproducibility is desired.

---

*This note is a clarification companion. Where it conflicts with the `.docx` on Office-Connect's hosting substrate, this note governs (per the author's 2026-07-22 decision); on everything else, the execution plan governs. When convenient, fold the C-4 override and the §2 deployment mapping into the `.docx` so the source of truth is self-consistent.*
