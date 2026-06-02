# Tenant-Isolation Requirements Checklist: WhatsApp Direct Send Broadcasts (OrderStatus)

**Purpose**: Validate that the SPEC, PLAN, RESEARCH, and CONTRACTS clearly specify tenant-isolation requirements for the Direct Send pipeline — so a project NEVER dispatches through another project's templates, channel app, or Meta credentials, and every database query, EDA payload, and Meta call is scoped by `project_uuid` (directly or via a documented FK chain).

**Created**: 2026-05-20

**Feature**: [spec.md](../spec.md)

**Scope**: All three concrete attack surfaces named by the user — (a) DB queries (Template / Version / IntegratedAgent / BroadcastMessage / BroadcastConversion / Credential), (b) EDA payloads (RabbitMQ inbound status-update consumer, datalake outbound events), (c) Meta calls (library-catalog GET at assignment, Direct Send dispatch via Flows-then-Meta) — plus the channel-app GET (Integrations Engine) because the Direct Send flag and channel credentials live there.

**Audience / timing**: PR reviewer pre-merge. This checklist is "unit tests for English" — every item validates the QUALITY OF REQUIREMENTS (do the spec, plan, contracts state what must be true?), not the correctness of any implementation.

---

## Requirement Completeness — The Tenant-Isolation Invariant

- [x] CHK001 Is the tenant-isolation invariant ("a project MUST NEVER dispatch through, read, or write data scoped to another project") stated as an explicit requirement in `spec.md` (or only implied by the `Project` FK chain)? [Gap]
- [x] CHK002 Is the canonical tenant identifier defined unambiguously (`Project.uuid` Retail-internal vs. `vtex_account` external vs. `IntegratedAgent.uuid` per-agent vs. `channel_uuid` per-channel)? [Clarity, Gap]
- [x] CHK003 Is the boundary of "tenant" defined — is it one project = one tenant, or does an agent + project pair form a finer-grained tenant (relevant for multi-agent projects)? [Clarity, Gap]
- [x] CHK004 Is "credentials" defined unambiguously — the user query says "Meta credentials" but the codebase has FOUR distinct credential surfaces: (a) the global `META_SYSTEM_USER_ACCESS_TOKEN`, (b) per-channel WhatsApp Cloud credentials held by Integrations, (c) the Flows internal-auth token, (d) per-agent `Credential` rows. [Ambiguity, Gap]

## Requirement Completeness — DB Query Scoping

- [x] CHK005 Is "every DB query that touches `Template`, `Version`, `IntegratedAgent`, `Credential`, `BroadcastMessage`, or `BroadcastConversion` MUST be scoped by `project` (directly or via FK chain)" stated as an architectural requirement? [Gap]
- [x] CHK006 Is the canonical FK chain `Template → IntegratedAgent → Project` documented as the dispatch-path scoping mechanism? [Completeness, data-model.md §1]
- [x] CHK007 Is the dual-path project scoping on `Template` documented and reconciled — `Template.integrated_agent.project` (transitive) vs. `Template.versions[].project` (direct FK on `Version`)? Should both project references always agree? [Clarity, Consistency, Gap]
- [x] CHK008 Is the uniqueness scope of `Template.name` documented (global vs. per-IntegratedAgent vs. per-project)? Two projects assigning OrderStatus would each persist a Template named `weni_order_invoiced` — without a documented scope, a future migration could re-introduce a global unique constraint and silently break tenant isolation. [Gap]
- [x] CHK009 Is the uniqueness scope of `Version.template_name` documented (global vs. per-project)? The Direct Send identifier is per-WABA; Retail's local uniqueness must align with that. [Clarity, Gap]
- [x] CHK010 Is the referential-integrity requirement "`Version.integrations_app_uuid` MUST be the channel app of the same project as `Version.project`" stated and enforceable? [Gap]
- [x] CHK011 Is the referential-integrity requirement "`Template.integrated_agent.project == Version.project` for every (Template, Version) pair" stated as an invariant the system MUST preserve? [Gap]

## Requirement Completeness — EDA / Consumer Scoping

- [x] CHK012 Is the inbound RabbitMQ status-update consumer's tenant-scoping requirement specified? Today the consumer matches by `broadcast_id` / `external_message_id` without an explicit project filter; the spec should state whether this is acceptable defense-in-depth or a `[Gap]`. [Gap]
- [x] CHK013 Is the EDA event-payload schema documented (which fields carry the tenant identifier — `broadcast_id`? `external_message_id`? `project_uuid`?), and is `project_uuid` required or optional? [Gap]
- [x] CHK014 Is the assumption "Flows guarantees `broadcast_id` global uniqueness across all Weni tenants" stated explicitly as a tenant-isolation precondition? Without it, the consumer's project-less lookup is unsafe. [Assumption, Gap]
- [x] CHK015 Is the behavior defined when an EDA event arrives whose `broadcast_id` matches a `BroadcastMessage` in project A but the event's payload references project B? Should the event be dropped, logged, persisted, raised? [Coverage, Edge Case, Gap]
- [x] CHK016 Is the `mark_broadcast_converted` flow's tenant scoping documented (the `(project, order_id)` unique constraint is the boundary; the requirement should restate this)? [Completeness, data-model.md]

## Requirement Completeness — Meta Call Scoping

- [x] CHK017 Is the use of a SINGLE `META_SYSTEM_USER_ACCESS_TOKEN` for ALL projects' library-catalog reads documented as a deliberate cross-tenant credential, with the rationale ("Meta library catalog is a global resource")? [Assumption, Plan §Constraints, Gap]
- [x] CHK018 Is the property "Meta library catalog is GLOBAL — not per-WABA, not per-project" stated in `contracts/meta-library-catalog.md` as a tenant-isolation observation? Without it, a reader could assume the system token grants per-tenant access. [Clarity, contracts/meta-library-catalog.md, Gap]
- [x] CHK019 Is the property "Direct Send DISPATCH (POST to Flows → POST to `<PHONE_NUMBER_ID>/messages`) uses the project's CHANNEL credentials, NOT the system token" documented as the per-tenant boundary at dispatch time? [Clarity, contracts/messaging-gateway-payload.md, Gap]
- [x] CHK020 Is "leaked tenant data via the library-catalog GET is impossible because the catalog returns only Meta-curated public templates" stated and validated as a security claim? [Assumption, Gap]
- [x] CHK021 Is the requirement "the local `Template.metadata.direct_send.fetched_from_meta_library=True` audit trail records that the content came from a global resource (so a future audit can distinguish per-tenant from cross-tenant content sources)" stated? [data-model.md §3, Gap]

## Requirement Completeness — Channel App Scoping (Integrations Engine)

- [x] CHK022 Is the assignment-time validation "the `app_uuid` query param MUST be cross-validated against the `Project-Uuid` header to ensure the channel belongs to the project being assigned" stated as a requirement? [Gap, contracts/integrations-channel-app.md §1]
- [x] CHK023 Is `IntegrationsService.get_channel_app(...)` required to verify (or document the assumption) that the returned app's `project_uuid` matches the assignment's project? Today the service returns the raw response without that check. [Gap, contracts/integrations-channel-app.md §2]
- [x] CHK024 Is the failure mode specified when the app's `project_uuid` doesn't match the request's `Project-Uuid` (treat as channel-lookup failure → `direct_send=False` + warning, OR deny assignment outright with an error response)? [Coverage, Gap]
- [x] CHK025 Is "operator with permission on project A passes project B's `app_uuid` in the assignment request" documented as a known attack vector that the request validation must reject? [Coverage, Edge Case, Gap]

## Requirement Clarity — Project Identifiers in External Calls

- [x] CHK026 Is the relationship between `Project.uuid` (Retail-internal) and `Project.vtex_account` (external) documented as one-to-one, and is the consequence of a duplicate `vtex_account` ("`MultipleObjectsReturned` → return None") stated as a security boundary, not just a quirk? [Clarity, Spec §Assumptions, Gap]
- [x] CHK027 Is the `Agent.project` FK scoping documented as the per-project Lambda boundary (Lambda function name `retail-setup-{hash_13_digits}` derived from agent name + agent UUID, where the agent is per-project)? [Completeness, Gap]
- [x] CHK028 Is the `channel_uuid` field on `IntegratedAgent` documented as a per-project channel identifier, and the requirement "two IntegratedAgents in different projects MUST NEVER share the same `channel_uuid`" stated? [Gap]

## Requirement Consistency — Cross-Pipeline Tenant Boundary

- [x] CHK029 Are dispatch-path and assignment-path tenant-scoping rules CONSISTENT (both keyed by project, neither relying on agent UUID alone for tenant determination)? [Consistency, Gap]
- [x] CHK030 Are `PAUSED` / `FLAGGED` status checks scoped per-project (so flipping a Version's status in project A's Template MUST NOT affect any other project's broadcasts)? Today this is structurally guaranteed via the `Version.template` FK chain; the requirement should restate it explicitly. [Consistency, Gap]
- [x] CHK031 Is the `IntegratedAgent.config["initial_template_language"]` per-project property reconciled with the per-project content fetched at assignment time (project A's `pt_BR` content does not bleed into project B's `es_MX` content even though both fetches use the same Meta system token)? [Consistency, plan.md, Gap]

## Acceptance Criteria — Measurable Tenant Isolation

- [x] CHK032 Can "no cross-project data leakage" be objectively measured (e.g. via a SQL audit query that joins `BroadcastMessage` to `IntegratedAgent` and asserts `BroadcastMessage.project == IntegratedAgent.project`)? [Measurability, Gap]
- [x] CHK033 Are SC-003 and SC-004 verifiable per-project in isolation (so a regression that mixes traffic between two test projects fails the metric instead of getting averaged out)? [Measurability, Spec §SC-003, Spec §SC-004]
- [x] CHK034 Can "every DB query is scoped by project" be turned into a runtime invariant check (e.g. a Django middleware / queryset wrapper) — and if so, is the requirement to instrument or audit it stated? [Measurability, Gap]

## Scenario Coverage — Cross-Tenant Attack Vectors

- [x] CHK035 Is the "Flows status callback misroutes a `delivered` event to the wrong tenant's BroadcastMessage" attack vector specified? [Coverage, Edge Case, Gap]
- [x] CHK036 Is the "two projects share a VTEX account due to data error → order-status webhook routes to the wrong project" attack vector specified? [Coverage, Edge Case, Gap]
- [x] CHK037 Is the "operator on project A assigns the OrderStatus agent passing project B's `channel_uuid`" attack vector specified? [Coverage, Edge Case, Gap]
- [x] CHK038 Is the "rule engine (Lambda) for project A returns a `template` name that happens to match project B's local Template name" path specified — and is the per-IntegratedAgent template lookup (`integrated_agent.templates.filter(name=...)`) confirmed as the safety net? [Coverage, Edge Case, Gap]
- [x] CHK039 Is the "re-assignment after `is_active=False` re-attaches to a previous Template owned by a different project" race specified? [Coverage, Edge Case, Gap]

## Non-Functional Requirements — Cache & Datalake Tenant Isolation

- [x] CHK040 Are cache keys documented as project-scoped (`order_status_event:{project_id}:{integrated_agent.uuid}:...`, `project_by_vtex_account_{vtex_account}`)? Without documentation, a future cache-key change could merge tenants silently. [NFR, Completeness, Gap]
- [x] CHK041 Is the datalake / `weni_datalake_sdk` event payload required to carry `project=str(integrated_agent.project.uuid)` so downstream analytics never aggregates across tenants? Today the implementation includes it; the requirement should state it. [NFR, Assumption, Gap]
- [x] CHK042 Is the audit-log shape for skip events (PAUSED/FLAGGED skip, dedup skip, naming-rule violation skip) documented as carrying `project_uuid` so an operator can filter logs by tenant? [Completeness, Gap]
- [x] CHK043 Is the requirement "Sentry / Elastic APM tags on every span MUST include `project_uuid`" stated, so production troubleshooting never crosses tenants? [NFR, Plan §Stack, Gap]

## Dependencies & Assumptions — Upstream Tenant Models

- [x] CHK044 Is the dependency on Integrations Engine to enforce channel-app-to-project ownership documented as a tenant-isolation precondition (Retail TRUSTS Integrations to return `config.direct_send` for the channel of the requested project)? [Dependency, Gap, contracts/integrations-channel-app.md]
- [x] CHK045 Is the assumption "the AWS Lambda IAM role / function-name namespace prevents cross-tenant invocation by name" documented (function names are derived from `agent.uuid` which is per-project)? [Assumption, Gap]
- [x] CHK046 Is the assumption "VTEX `defaultLocale` per tenant never aliases across projects" documented (so the locale-driven Meta library fetch can never accidentally map two projects' to the same fetch result)? [Assumption, Gap]

## Ambiguities & Conflicts

- [x] CHK047 Is the relationship between Retail's local template-name uniqueness and Meta's Direct Send Beta requirement ("template_name MUST be unique within your WABA") documented? Each project has its own WABA, so per-WABA uniqueness should map to per-project uniqueness in Retail — but the spec doesn't make this mapping explicit. [Clarity, Gap]
- [x] CHK048 Does the spec resolve the conflict between "the operator can retry once Meta has the content" (Spec §Edge Cases) and the fact that retry uses the SAME global system token (so a transient cross-tenant Meta rate-limit could block ALL projects' assignments simultaneously)? [Conflict, Gap]
- [x] CHK049 Is the spec's "channel_uuid is per-project" claim made explicit and verified, rather than left as an inference from the model FK? [Ambiguity, Gap]

---

## Notes

- 49 items, organized into 12 quality-dimension categories. Coverage spans the three attack surfaces named in the user query (DB queries, EDA payloads, Meta calls) plus the channel-app GET surface (where the per-tenant Direct Send flag lives) and the cross-cutting concerns (cache, datalake, observability).
- Every item is phrased as a question about the WRITTEN REQUIREMENTS, not about runtime correctness. Failing items should be resolved by amending `spec.md`, `plan.md`, `research.md`, or `contracts/*.md` — not by adding a code workaround.
- Markers used: `[Gap]`, `[Ambiguity]`, `[Conflict]`, `[Assumption]`, plus traceability references to `[Spec §X]`, `[Plan §X]`, `[Contract:X]`, and `[data-model.md §X]`. 100% of items carry at least one marker.
- One genuine `[Conflict]` was surfaced at CHK048 (single global Meta system token vs. per-tenant retry independence). Worth resolving before merge, or explicitly accepting the trade-off in `Plan §Constraints`.
- The schema verification done at checklist-generation time confirmed that `Template.name` and `Version.template_name` are NOT globally unique today (`unique=True` was removed in later migrations), so CHK008 / CHK009 are framed as `[Gap]` (missing documentation) rather than `[Conflict]`. A future migration that re-introduces a global unique constraint would silently break multi-tenant Direct Send and is the exact regression these items defend against.
- Cross-reference: `requirements.md` covers spec quality at the macro level; `idempotency.md` covers retry-safety; THIS checklist covers tenant isolation. The three are complementary and intentionally non-overlapping.

## Resolution Map (validation iteration 1 — 2026-05-21)

Every item above was resolved by amending the source documents
listed below. Reviewers can verify by reading the named section /
FR / Decision / Contract clause.

### Spec (`spec.md`)

- **Named Invariant — Tenant Isolation** + §Canonical tenant identifier + §Tenant boundary + §Tenant FK chain + §Multi-credential surface taxonomy — CHK001, CHK002, CHK003, CHK004.
- **FR-040** (every DB query scoped by project; queryset audit at code review) — CHK005, CHK029, CHK034.
- **FR-041** (inbound EDA consumer tenant resolution; project-payload-vs-row mismatch handling) — CHK012, CHK013, CHK014, CHK015.
- **FR-042** (datalake / EDA outbound `project` required field) — CHK041.
- **FR-043** (`app_uuid` ↔ `Project-Uuid` cross-validation; v1 transitive trust + defense-in-depth follow-up; persisted `channel_uuid` snapshot) — CHK022, CHK023, CHK024, CHK025, CHK028, CHK037, CHK049.
- **FR-044** (audit log + Sentry / APM span tags include `project_uuid`) — CHK042, CHK043.
- **FR-045** (per-IntegratedAgent uniqueness scope on `Template.name` / `Version.template_name`; per-WABA = per-IntegratedAgent mapping) — CHK008, CHK009, CHK047.
- **FR-046** (PAUSED / FLAGGED tenant-scoped via FK chain) — CHK030.
- **SC-010** (no-cross-project-data-leakage measurable invariants; per-project SC-003 / SC-004 measurability) — CHK032, CHK033.
- **Edge Cases** (operator on A passes B's `app_uuid`, Flows callback misroute, two projects share VTEX account, Lambda template-name collision, re-assignment, EDA payload-vs-row project mismatch, single Meta system token rate-limit) — CHK015, CHK025, CHK035, CHK036, CHK037, CHK038, CHK039, CHK048.
- **Assumptions** (Lambda function-name namespace per-project, VTEX `defaultLocale` non-aliasing, channel-app upstream trust, Meta library catalog global, Flows `broadcast_id` global uniqueness, cache keys project-scoped, datalake events carry tenant identifier) — CHK014, CHK017, CHK040, CHK041, CHK044, CHK045, CHK046.

### Plan (`plan.md`)

- **Constraints — Tenant isolation** (canonical tenant identifier, FK chain, multi-credential surface taxonomy, cache key project-scoping, EDA tenant tagging, observability tags, Lambda namespace, FR-043 v1 implementation status, runtime invariant audit T035c) — CHK017, CHK034, CHK040, CHK041, CHK042, CHK043, CHK045.
- **Complexity Tracking** updated to reflect that all four checklists are resolved.

### Research (`research.md`)

- **Decision 16 — Tenant Isolation Model** (canonical identifier, FK chain, credential surface taxonomy, EDA consumer tenant resolution, cache project-scoping, Lambda namespace, FR-043 v1 implementation status, single-Meta-token cross-tenant rate-limit conflict resolution, alternatives considered) — CHK002, CHK003, CHK004, CHK006, CHK048.

### Data model (`data-model.md`)

- **§7.1 Tenant FK chain (canonical scoping)** — CHK006, CHK007.
- **§7.2 Referential-integrity invariants** (BroadcastMessage / Conversion / Template / Version cross-FK invariants; per-IntegratedAgent uniqueness on `Template.name` / `Version.template_name`; `channel_uuid` per-project) — CHK008, CHK009, CHK010, CHK011, CHK028, CHK032.
- **§7.3 PAUSED / FLAGGED status checks tenant-scoped via FK chain** — CHK030.
- **§7.4 BroadcastConversion tenant boundary** — CHK016.

### Contracts

- `contracts/integrations-channel-app.md` **§8 Tenant-isolation requirements** (cross-validation requirement, v1 implementation status, persisted snapshot) + **§9 Upstream dependency on Integrations Engine** (channel-app authorization + channel UUID global uniqueness as preconditions) — CHK022, CHK023, CHK024, CHK025, CHK028, CHK044, CHK049.
- `contracts/meta-library-catalog.md` **§9 Tenant isolation** (single global system token as cross-tenant credential, library catalog as global Meta-curated public resource, cross-tenant rate-limit blast radius, audit trail records cross-tenant content source, per-project atomic-rollback boundary) — CHK017, CHK018, CHK020, CHK021, CHK048.
- `contracts/messaging-gateway-payload.md` **§8 Tenant isolation** (per-tenant credentials at dispatch vs cross-tenant Meta system token at assignment, required `project` field, EDA consumer tenant resolution, datalake event tenant tagging) — CHK019, CHK031, CHK041.

### Items resolved by referring to existing requirements (no new text was needed beyond the FRs above)

- **CHK016** (`mark_broadcast_converted` tenant scoping) — already implicit in spec FR-033 (`(project, order_id)` unique constraint); `data-model.md` §7.4 makes it explicit.
- **CHK029** (dispatch-path and assignment-path consistency) — both paths already key by project per FR-040; the consistency is restated in FR-040 + FR-046.
- **CHK031** (`initial_template_language` per-project) — already pinned in spec.md Clarifications and FR-003b; Edge Case "VTEX `defaultLocale` per tenant never aliases" + Assumption documents the tenant boundary at locale resolution; `contracts/messaging-gateway-payload.md` §8 confirms per-project content materialization.
- **CHK038** (Lambda template-name collision) — covered by Edge Case "Lambda for project A returns a `template` name that happens to match project B's local Template name" + FR-045 (per-IntegratedAgent uniqueness scope).
- **CHK039** (re-assignment after `is_active=False`) — covered by Edge Case "Re-assignment after `is_active=False`..." in spec.md (already restating that re-assignment is a NEW IntegratedAgent row; the previously-persisted Templates remain FK-linked to their original IntegratedAgent).

Every CHK item maps to at least one FR / Decision / Contract clause introduced or restated in this iteration. No item required leaving a `[Gap]` open — the resolution map is complete.
