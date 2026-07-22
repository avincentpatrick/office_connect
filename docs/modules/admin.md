# Module: Admin (Rooms & Announcements)

## 1. Status

**NOT STARTED. Phase slot: 9.**

## 2. Purpose

Room booking and announcements for the bureau: bookings host activities,
announcements surface on the landing shell, both feed the Calendar of
Activities output.

## 3. Source references

- `references/OfficeConnect_Build_Execution_Plan_v1_0.docx` Phase 9 (Module 3)
- `references/Digital_Transformation_Integration_Blueprint.md` §3/§6

## 4. Integration obligations (Blueprint §3/§6)

- `activity_id` (nullable) on room bookings — one optional "what is this room
  for?" picker.
- Bookings feed the **Calendar of Activities (CY)** generator (mandated
  output #8) together with the activity registry and announcements.
- Optional document ↔ booking soft-ref ("minutes of") with DMWIS.

## 5. Open decisions

- Table set under `admin_*` (pluralized per DB standards §2).

## 6. Plan

*(Filled at the module's requirements session.)*
