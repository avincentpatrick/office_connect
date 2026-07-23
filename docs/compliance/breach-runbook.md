# Personal Data Breach — Response Runbook

Per **RA 10173 / NPC Circular 16-03**: notify the NPC and affected data subjects
**within 72 hours** of knowledge of a notifiable breach, and submit the full
report within **5 days** (unless extended). This runbook is the standing
procedure; keep a printed + off-box copy (ops §3.2).

## 0. Roles
- **Incident lead** (DPO or delegate), **technical responder**, **comms**.

## 1. Detect & triage (immediately)
- Record: what was observed, when, by whom; the request ids / account(s)
  involved; systems affected.
- Classify: is personal data / SPI involved? Confidentiality, integrity, or
  availability? Is it **notifiable** (SPI or data that may enable identity
  fraud, and real risk of serious harm)?

## 2. Contain (hours 0–4)
- Revoke/rotate credentials of implicated accounts; the `oc_app` role cannot
  DELETE, which bounds destructive impact.
- Preserve evidence — **do not** alter the hash-chained audit log; snapshot it.
- Take affected surfaces offline if active exfiltration is suspected.

## 3. Investigate — the "what did account X touch between T1 and T2" query pack
Run against `core_audit_logs` (hash-chained; `verify_chain()` proves integrity):

```sql
-- Every audited change by an actor in a window
SELECT id, created_at, table_name, row_pk, action, request_id
FROM core_audit_logs
WHERE actor_id = :account_id
  AND created_at BETWEEN :t1 AND :t2
ORDER BY id;

-- Everything that happened under a suspect request id
SELECT * FROM core_audit_logs WHERE request_id = :request_id ORDER BY id;

-- Reads (privacy-preserving; ids/params only) in the window
SELECT * FROM core_query_logs
WHERE created_by = :account_id AND created_at BETWEEN :t1 AND :t2
ORDER BY id;
```
Also review structured JSON logs filtered by `request_id`, and the error tracker
if enabled.

> **TODO (Stage B):** a small incident table + a CLI wrapper for this query pack
> once `core_users` exists (so `actor_id` resolves to a person).

## 4. Assess & decide notification
- Determine scope (records, subjects, data types) and risk of harm.
- If notifiable: prepare NPC notification + data-subject notice.

## 5. Notify (within 72 hours of knowledge)
- **NPC**: nature of breach, personal data involved, measures taken, contact.
- **Data subjects**: nature, likely consequences, measures, how to protect
  themselves.
- Submit the **full report within 5 days**.

## 6. Remediate & learn
- Close the root cause; add a control (and a test if it is a software defect).
- Record in the incident log; schedule a post-incident review.
