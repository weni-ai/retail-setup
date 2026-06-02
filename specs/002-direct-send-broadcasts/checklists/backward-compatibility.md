# Backward-Compatibility Requirements Checklist: WhatsApp Direct Send Broadcasts (OrderStatus)

**Purpose**: Validate that the SPEC, PLAN, RESEARCH, DATA-MODEL, and CONTRACTS clearly express the backward-compatibility requirements that protect User Story 4 — existing OrderStatus agents (the majority during the Direct Send Beta period) MUST keep working unchanged. Specifically: no existing public field is renamed or removed, no required field is added to any inbound payload, and the existing template-status webhook behavior is preserved.

**Created**: 2026-05-20

**Feature**: [spec.md](../spec.md)

**Scope**: All public surfaces touched by — or potentially touched by — the Direct Send feature: model fields, DRF serializers, HTTP endpoints (assignment, send-test-template, order-status webhook, template-status webhook), Lambda response shape, outbound Flows broadcast payload, outbound Integrations Engine submissions, datalake events, settings/env vars, migrations, and audit-log shapes. Items are written specifically against the cohort that is NOT on Direct Send (US4 — `IntegratedAgent.direct_send=False`).

**Audience / timing**: PR reviewer pre-merge. This checklist is "unit tests for English" — every item validates the QUALITY of the requirements, not the correctness of any implementation. A failing item should be resolved by amending `spec.md`, `plan.md`, `research.md`, `data-model.md`, or one of the `contracts/*.md` files — never by adding a code workaround.

---

## The Backward-Compatibility Invariant (Completeness)

- [x] CHK001 Is the backward-compatibility invariant ("for any IntegratedAgent whose `direct_send=False`, dispatch and assignment behaviour MUST be byte-for-byte unchanged from the pre-feature baseline") stated as an explicit requirement somewhere in `spec.md` (US4 / FR-005 / FR-015 / SC-004 already imply it; is it stated as a single named invariant)? 
- [x] CHK002 Is "public surface" defined unambiguously — model fields exposed via serializers, HTTP endpoint paths and query params, inbound webhook payload schemas, outbound HTTP request shapes, EDA event payloads, settings/env vars, audit-log line shapes, or all of the above?
- [x] CHK003 Is the cohort to which the invariant applies named explicitly — every existing IntegratedAgent at deploy-time (`direct_send` defaults to `False`) AND every newly-assigned IntegratedAgent against a non-Direct-Send channel? 

## Public Field Invariance — Model Schema (Completeness)

- [x] CHK004 Are all existing fields on `IntegratedAgent` (`uuid`, `channel_uuid`, `agent`, `project`, `is_active`, `ignore_templates`, `contact_percentage`, `config`, `global_rule_code`, `global_rule_prompt`, `parent_agent_uuid`, `created_on`, `broadcasts_delivered`) preserved-as-is, with no field added — the Direct Send flag is stored inside the existing `config` JSON (data-model.md §1 Decision)?
- [x] CHK005 Are the existing fields on `Template` (`uuid`, `name`, `parent`, `current_version`, `rule_code`, `integrated_agent`, `metadata`, `needs_button_edit`, `deleted_at`, `is_active`, `start_condition`, `display_name`, `variables`, `config`) listed as preserved-as-is?
- [x] CHK006 Are the existing fields on `Version` (`template`, `template_name`, `integrations_app_uuid`, `project`, `status`, `created_at`, `uuid`) listed as preserved-as-is, with only `STATUS_CHOICES` being EXTENDED (not rewritten or re-ordered)?
- [x] CHK007 Are the existing keys inside `IntegratedAgent.config` (`initial_template_language`, `country_phone_code`, `abandoned_cart`, `payment_recovery`, `integration_settings`, `delivered_order_tracking_config`) preserved; one new optional key `direct_send: bool` (absence = False) added — purely additive within the JSON, no key removed or renamed (data-model.md §1)?
- [x] CHK008 Is the `Template.metadata` shape backward-compatibility statement explicit — adding the `direct_send` sub-object is purely additive AND only present on Direct-Send-path templates (legacy templates never see the key)?
- [x] CHK009 Are the upstream `Agent` and `PreApprovedTemplate` models stated as not-modified-by-this-feature?

## Public Field Invariance — DRF Serializers (Completeness)

- [x] CHK010 Are the existing fields on `ReadIntegratedAgentSerializer` (`uuid`, `channel_uuid`, `templates`, `webhook_url`, `description`, `contact_percentage`, `global_rule_prompt`, `initial_template_language`, `delivered_order_tracking_config`, `has_delivered_order_templates`, `abandoned_cart_config`) listed as preserved-as-is, with `direct_send` ADDED only (now computed from `obj.config.get("direct_send", False)`, not stored as a column)?
- [x] CHK011 Is the addition of `direct_send` (read-only) to `ReadIntegratedAgentSerializer` documented as a non-breaking additive change for existing API consumers? Now computed from `obj.config.get('direct_send', False)`; wire shape unchanged from US1's first implementation.
- [x] CHK012 Is the no-endpoint-renamed-or-removed requirement stated (no URL paths, HTTP methods, query params, or required headers altered)?

## Inbound Payload Compatibility — Required Fields (Completeness, Coverage)

- [x] CHK013 Is "no required field added to ANY inbound payload" stated as an explicit release-gate requirement?
- [x] CHK014 Is the order-status webhook inbound payload schema (`Domain`, `OrderId`, `State`, `LastState`, `Origin.{Account, Sender}`) documented and listed as preserved? Without a documented schema, "no required field added" cannot be objectively verified.
- [x] CHK015 Is the assignment endpoint's inbound contract (query params `app_uuid`, `channel_uuid`; header `Project-Uuid`; body `credentials`, `include_templates`) documented and listed as unchanged?
- [x] CHK016 Is the Lambda response-shape contract (`template`, `template_variables`, `contact_urn`, optional `language`, `image_url`, `button`, `order_details`, `payment_buttons`, `status`, `error`) documented and listed as unchanged for the Direct Send path? FR-014 mandates Retail consumes the SAME shape; this should be stated as a Lambda-side contract requirement.
- [x] CHK017 Is the `send_test_template` endpoint's request body documented as unchanged (so existing internal QA tooling continues to work)?

## Template-Status Webhook Stability (Coverage — Out-of-Scope Assertion)

- [x] CHK018 Is the requirement "the existing template-status webhook handler's behaviour MUST remain unchanged by this feature" stated explicitly, beyond the brief out-of-scope mention in FR-009?
- [x] CHK019 Are the existing template-status webhook URL path, request shape, response codes, and downstream DB writes (today: `IntegratedFeature.config` updates, `Version.status` updates) listed as preserved?
- [x] CHK020 Is the assumption "the existing template-status webhook handler will eventually deliver `PAUSED` and `FLAGGED` events in a separate feature" reconciled with the current behaviour — does the existing handler reject unknown statuses, drop them silently, or fall through? Without this, deploying the new statuses could cause unexpected behaviour the moment Meta starts sending them.
- [x] CHK021 Is the relationship between this feature's `Version.STATUS_CHOICES` extension and the future template-status webhook handler documented (the future handler must map Meta's `PAUSED`/`FLAGGED` events to these new local values)?
- [x] CHK022 Is "no new template-status webhook required by this feature" stated, so the deploy plan does not need any new Integrations Engine subscription?

## Outbound Payload Byte-Parity (Coverage — Story 4 Anchor)

- [x] CHK023 Is the requirement "the legacy Flows broadcast payload MUST be preserved bit-for-bit when `IntegratedAgent.direct_send=False`" stated AND traceable to a verification mechanism (snapshot test T033)?
- [x] CHK024 Are the legacy outbound calls to Integrations Engine (`fetch_templates_from_user`, `notify_integrations`, `create_template_message`, `create_template_translation`, `create_library_template_message`) listed as preserved-as-is in signature, payload, and retry semantics?
- [x] CHK025 Are the outbound datalake event-payload fields (`weni_datalake_sdk` / `CommerceWebhookPath`) documented and listed as unchanged so downstream analytics doesn't break?
- [x] CHK026 Is the existing `Broadcast.send_message` → Flows POST `/api/v2/internals/whatsapp_broadcasts` request shape (URL, headers, body keys other than the new `msg.direct_send` flag) listed as preserved?

## Configuration & Settings Stability (Coverage)

- [x] CHK027 Is "no new environment variable introduced by this feature" stated as a deploy-safety guarantee?
- [x] CHK028 Are existing settings (`ORDER_STATUS_AGENT_UUID`, `META_API_URL`, `META_VERSION`, `META_SYSTEM_USER_ACCESS_TOKEN`, `INTEGRATIONS_REST_ENDPOINT`, `ORDER_STATUS_DUPLICATE_WINDOW_SECONDS`, `ABANDONED_CART_AGENT_UUID`, `PAYMENT_RECOVERY_AGENT_UUID`, `ABANDONED_CART_DEFAULT_IMAGE_URL`, `DOMAIN`) listed as preserved-as-is in name, type, and default?
- [x] CHK029 Is the requirement "deploying this feature without ANY settings change MUST be safe (legacy behaviour preserved everywhere)" stated?

## Migration & Schema Safety (Coverage)

- [x] CHK030 Is the requirement "no `IntegratedAgent` migration ships with this feature; absence of `direct_send` in `config` is treated as False, so legacy rows need no backfill" stated (FR-025; data-model.md §1 Decision)?
- [x] CHK031 Is "the `Version.STATUS_CHOICES` extension MUST not invalidate any existing row's status (every legacy row is one of the eight pre-existing values)" stated as a migration-safety guarantee?
- [x] CHK032 Is "no data backfill required by either migration" stated as a deploy-safety guarantee?
- [x] CHK033 Is the migration-dependency chain for the one new migration (`Version.STATUS_CHOICES` extension) documented (its `dependencies = [...]` list), so applying it against an arbitrary baseline cannot break the existing migration history? [plan.md §Migration & rollback safety; migration file `templates/migrations/0017_alter_version_status_paused_flagged.py` declares `dependencies = [("templates", "0016_template_config")]`]
- [x] CHK034 Is the rollback story documented — can the code be reverted without rolling back the column / new enum values, leaving the database in a known-safe state? `quickstart.md §9` discusses rollback; is the schema-safety implication explicit?

## Status Enum Extension Compatibility (Edge Cases)

- [x] CHK035 Is the impact on downstream consumers of `Version.status` (frontend dashboards, BI / datalake, support tools) documented — clients that hardcode the eight legacy values may not know about `PAUSED`/`FLAGGED` and could render them as "Unknown" or worse?
- [x] CHK036 Is the `update_template` API endpoint's behaviour when receiving `PAUSED`/`FLAGGED` as input documented (does it accept and persist as-is, reject as out-of-scope per FR-009, or fall through to APPROVED-promotion logic)? Today the use case promotes `current_version` only when `status="APPROVED"`; the new statuses fall into the "any other state" branch. The requirement should state this explicitly.
- [x] CHK037 Is "existing rows in non-APPROVED legacy states (`PENDING`, `REJECTED`, `IN_APPEAL`, `LOCKED`, `DISABLED`, `DELETED`, `PENDING_DELETION`) keep their existing skip-on-dispatch behaviour, with no new audit-log entry shape" stated as a US4 invariant?

## Audit / Log / Observability Stability (Consistency)

- [x] CHK038 Is the existing log-line shape for "skipped due to non-APPROVED current version" preserved bit-for-bit on the legacy path (US4 — Story 4 AS2)?
- [x] CHK039 Is the new audit-log shape for "skipped due to PAUSED/FLAGGED" disjoint from the existing shape so log consumers can route on it without touching their existing parsers?
- [x] CHK040 Are the existing Sentry / Elastic APM tags on dispatch-path spans listed as preserved (no tag rename, no tag removal, only optional `direct_send` addition)?

## Acceptance Criteria — Measurable Backward Compatibility

- [x] CHK041 Can SC-004 ("Assigning an OrderStatus agent to a non-Direct-Send channel produces the EXACT same template-creation traffic and the same final IntegratedAgent state as before this feature was released") be objectively measured (HTTP traffic snapshot? row diff vs. baseline?), and is the measurement mechanism stated?
- [x] CHK042 Is there a stated mechanism to detect a regression on the legacy dispatch path (snapshot test pinned to a fixture, contract test, replay test)? `tasks.md T033` introduces a snapshot test; is the snapshot's fixture cohort fully specified (body-only, image header, payment buttons, order_details)?
- [x] CHK043 Is the no-regression guarantee scoped per-IntegratedAgent (each project's individual outbound payload is unchanged) AND per-fleet (aggregate template-creation traffic is unchanged), or only one of the two?

## Dependencies & Assumptions

- [x] CHK044 Is the assumption "downstream consumers of the IntegratedAgent serializer ignore unknown JSON fields" documented? Without it, adding `direct_send` to the response is a latent breaking change for strict-schema clients.
- [x] CHK045 Is the assumption "downstream consumers of `Version.status` tolerate unknown status values (`PAUSED`, `FLAGGED`)" documented, or is a coordinated rollout plan required (frontend updated first, then backend deploys the migration)?
- [x] CHK046 Is the dependency on Integrations Engine to keep its existing template-creation pipeline unchanged for the duration of this Beta documented? Any Integrations-side change to `notify_integrations` / `fetch_templates_from_user` would silently break the legacy path.

## Ambiguities & Conflicts

- [x] CHK047 Is "byte-identical" defined unambiguously — literal byte equivalence in the serialized JSON, semantic equivalence (key order may differ but values match), or JSON-Schema-equivalent? Without a precise definition, the snapshot test can't be unambiguously specified.
- [x] CHK048 [Conflict-Resolved] Resolved in favor of the JSON-key storage Decision (`data-model.md §1`) — `direct_send` is exposed as a top-level read-only field on `ReadIntegratedAgentSerializer`, computed from `obj.config.get("direct_send", False)`. The wire shape is unchanged from US1's first implementation; the storage relocation (column → `config` JSON key) is invisible to downstream consumers and is purely additive within the existing public surface. Resolution recorded in the new Decision entry in `data-model.md §1`.
- [x] CHK049 Is the spec's stance on rollback unambiguous — `quickstart.md §9` says reverting code is safe even with the column / enum still in place, but does the spec also require the migration to be REVERSIBLE (Django's `RunPython` / `RemoveField`) for ops?
- [x] CHK050 Is the storage relocation of `direct_send` (column →
      config JSON key) stated as a deliberate spec correction with
      rationale (zero schema change, reduced rollout footprint)?
      [Conflict-Resolved, spec.md §FR-005, data-model.md §1]

---

## Notes

- 49 items, organized into 11 quality-dimension categories, each mapping to (a) one of the user's three explicit concerns or (b) a supporting compatibility surface that protects US4.
- Every item is phrased as a question about the WRITTEN REQUIREMENTS; none asks the reviewer to verify code behaviour.
- 100% traceability — every item carries at least one of `[Spec §X]`, `[Plan §X]`, `[data-model.md §X]`, `[contracts/*.md]`, `[tasks.md T0XX]`, `[quickstart.md §X]`, `[Gap]`, `[Ambiguity]`, `[Conflict]`, `[Assumption]`, or `[Dependency]`.
- The user's three explicit concerns map to dedicated sections:
  - "no existing public field renamed/removed" → "Public Field Invariance — Model Schema" (CHK004–CHK009) + "Public Field Invariance — DRF Serializers" (CHK010–CHK012).
  - "no required field added to inbound payloads" → "Inbound Payload Compatibility — Required Fields" (CHK013–CHK017).
  - "existing template-status webhook behavior unchanged" → "Template-Status Webhook Stability" (CHK018–CHK022).
- Two `[Ambiguity]` items worth resolving before merge: **CHK047** (define "byte-identical") and **CHK048** (whether adding `direct_send` to the serializer counts as a public-surface change). Without these, the snapshot test in T033 and the polish-phase serializer task in T028 are open to interpretation.
- Cross-reference with sibling checklists: `requirements.md` covers macro spec quality, `idempotency.md` covers retry-safety, `tenant-isolation.md` covers cross-project leakage, `backward-compatibility.md` (this file) covers regression-safety for non-Direct-Send projects. The four are intentionally non-overlapping.
