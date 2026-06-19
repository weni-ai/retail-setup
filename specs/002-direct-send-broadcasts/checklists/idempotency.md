# Idempotency & Retry-Safety Requirements Checklist: WhatsApp Direct Send Broadcasts (OrderStatus)

**Purpose**: Validate that the SPEC, PLAN, RESEARCH, and CONTRACTS clearly express the idempotency and retry-safety requirements for the Direct Send broadcast pipeline — so a single logical broadcast dispatches exactly once even when (a) the trigger event arrives twice, (b) any background task retries, or (c) Meta returns a 5xx mid-batch at agent-assignment time.

**Created**: 2026-05-20

**Feature**: [spec.md](../spec.md)

**Scope**: Both the synchronous **dispatch** path (US1: order-status webhook → Lambda → Flows → BroadcastMessage) and the synchronous **assignment** path (US2: operator → Meta library catalog batch fetch → IntegratedAgent + Templates), plus the asynchronous **inbound status-update consumer** that follows.

**Audience / timing**: PR reviewer pre-merge. This checklist is "unit tests for English" — every item validates the QUALITY OF REQUIREMENTS, not the correctness of an implementation.

---

## Requirement Completeness — Exactly-Once Dispatch Guarantee

- [x] CHK001 Is "exactly once" stated as an explicit delivery target somewhere in the requirements (or is it only implicit from the user-facing description of duplicate suppression)? [Gap]
- [x] CHK002 Is the boundary for "exactly once" defined — Retail-internal (no duplicate `BroadcastMessage` rows / no duplicate Flows POSTs) vs. end-to-end through Flows / Meta / customer device? [Clarity, Gap]
- [x] CHK003 Is "single logical broadcast" defined with the explicit tuple of identifiers that distinguishes it (project + integrated_agent + order_id + current_state? + template_name?)? [Clarity, Gap]
- [x] CHK004 Are the persistence-level idempotency keys for `BroadcastMessage` (`broadcast_id` unique-where-not-null, `external_message_id` unique-where-not-null) documented as REQUIREMENTS rather than left as code-only DB constraints? [Completeness, Spec §Assumptions]
- [x] CHK005 Is the `BroadcastConversion` uniqueness rule (one row per `(project, order_id)`) restated as a requirement and linked to the conversion-attribution flow that runs at most once per order? [Completeness, Gap]

## Requirement Completeness — Duplicate Trigger Suppression

- [x] CHK006 Is the order-status webhook duplicate-event suppression restated as an explicit requirement on the Direct Send dispatch path, or is it only carried by the spec's Assumptions section ("event sampling, deduplication … unchanged from today")? [Ambiguity, Spec §Assumptions]
- [x] CHK007 Is the dedup window length specified or referenced (e.g. `ORDER_STATUS_DUPLICATE_WINDOW_SECONDS`) at the requirement level so it can be tuned without spec amendment? [Clarity, Gap]
- [x] CHK008 Are the dedup-key components (`project`, `integrated_agent`, `order_id`, `current_state`) explicitly documented as the canonical idempotency key for trigger suppression? [Completeness, Gap]
- [x] CHK009 Is the behavior defined when two webhooks for DIFFERENT `current_state` (e.g. `invoiced` then `shipped` 50ms apart) arrive for the same `order_id`? [Coverage, Edge Case, Gap]
- [x] CHK010 Is the behavior defined when the official OrderStatus agent AND a custom agent with `parent_agent_uuid` both match the same project (current `_lookup_order_status_agent` fallback chain)? Should both dispatch, or should one suppress the other? [Coverage, Edge Case, Gap]

## Requirement Completeness — Async Task / Consumer Retry Safety

- [x] CHK011 Are retry semantics specified for the inbound RabbitMQ status-update consumer when it crashes after persisting a `BroadcastMessage` update but before acknowledging the broker? [Gap, Plan §Primary Dependencies]
- [x] CHK012 Are retry semantics specified for `mark_broadcast_converted` if the same `invoiced` event is delivered twice (broker re-delivery OR VTEX webhook duplicate)? [Coverage, Gap]
- [x] CHK013 Are retry semantics specified for `RecordBroadcastSentUseCase` when invoked twice for the same `broadcast_id` (e.g. transient DB error → caller retries)? [Coverage, Gap]
- [x] CHK014 Are max-attempts / dead-letter / poison-message requirements documented for ANY background task in the pipeline? [Gap]
- [x] CHK015 Is the `IntegratedAgent.broadcasts_delivered` counter's behavior under consumer re-delivery specified — must it stay idempotent across replays, or is double-counting acceptable? Today the implementation uses `F("broadcasts_delivered") + 1`, which is atomic but not idempotent. [Edge Case, Gap]

## Requirement Completeness — Mid-Batch External Failure (Meta 5xx at Assignment)

- [x] CHK016 Does FR-003d explicitly cover "Meta returns 5xx for one of N templates mid-batch", or only "missing translation in both languages"? The current wording groups them but doesn't separate transient vs. permanent failure. [Spec §FR-003d, Clarity]
- [x] CHK017 Is the operator-retry behavior after an FR-003d failure quantified (immediate retry allowed? cooldown? rate limit on consecutive retries against the same WABA)? [Spec §Edge Cases, Gap]
- [x] CHK018 Are auto-retry semantics specified for transient Meta 5xx — `Contract:meta §4` says "no retry policy in v1", but is this consistency-checked against the spec's expectation that the operator can retry "once Meta has the content (or recovers)"? [Consistency, Contract:meta §4, Spec §FR-003d]
- [x] CHK019 Is the "no caching of partial-batch results" property stated as a requirement so the operator's retry attempt re-fetches every template from scratch? [Gap, Plan §Constraints]
- [x] CHK020 Are the failure modes for the `pt_BR` fallback (FR-003c) distinguished between (a) `200` with empty `data` (translation missing), (b) `5xx` (Meta unreachable), and (c) malformed response — and is the requirement consistent across the three? [Spec §FR-003c, Clarity]

## Requirement Clarity — Idempotency Keys & Boundaries

- [x] CHK021 Are the conditional `BroadcastMessage` unique constraints (`broadcasts_broadcast_id_unique`, `broadcasts_external_message_id_unique`) documented as requirements with their conditions (`*_isnull=False`)? [Completeness, Gap]
- [x] CHK022 Is the multi-broadcast scenario for the same order (e.g. `invoiced` → `shipped` → `delivered` each producing a separate broadcast) reconciled with the `BroadcastConversion`'s ONE-row-per-(project, order_id) constraint? Which broadcast is attributed when multiple precede the `invoiced` event? [Consistency, Gap]
- [x] CHK023 Is "broadcast not dispatched" defined consistently — does it mean "no Flows POST issued" OR "no message reached the customer"? The PAUSED/FLAGGED skip path (Story 3) implies the former; the spec should state which. [Ambiguity, Spec §FR-012]

## Requirement Consistency — Cross-Pipeline Idempotency Model

- [x] CHK024 Are dedup semantics CONSISTENT between the legacy dispatch path (Story 4) and the Direct Send path (Story 1)? Story 4 mandates byte-identical legacy behavior, but the spec doesn't explicitly affirm that dedup keys / windows are identical. [Consistency, Spec §Assumptions]
- [x] CHK025 Are the audit-log entries for "skipped due to dedup", "skipped due to PAUSED/FLAGGED" (FR-012), and "skipped due to invalid Direct Send identifier" (FR-017 / Decision 7) distinguishable in shape so an operator can tell them apart? [Consistency, Coverage]
- [x] CHK026 Are Retail-side and Flows-side idempotency expectations aligned in `Contract:messaging-gateway-payload` — what is the documented behavior when Flows receives the same payload twice? Today the contract document is silent. [Contract:gateway, Gap]

## Scenario Coverage — Recovery & Compensation Flows

- [x] CHK027 Is the recovery flow defined when Flows returns 5xx but the message actually reached Meta (Retail records FAILED, customer received the message)? Today `_record_failed_dispatch` writes a FAILED row even on Retail-side timeout. [Recovery Flow, Gap]
- [x] CHK028 Is a manual re-dispatch flow for failed broadcasts defined as a requirement (operator runbook), or is it left to the implicit "rule engine fires again on the next webhook"? [Recovery Flow, Gap]
- [x] CHK029 Is the recovery flow defined for re-assignment of an OrderStatus agent after a previous assignment was unassigned (`is_active=False`) — does the new assignment re-fetch from Meta from scratch, or reuse the previous Templates? [Coverage, Gap]
- [x] CHK030 Is the recovery flow defined when the operator's retry after FR-003d races with a concurrent retry from a different operator on the same project? [Coverage, Edge Case, Gap]

## Edge Case Coverage — Race Conditions & Replays

- [x] CHK031 Is the "two concurrent webhooks for the same `(order_id, current_state)` racing across two workers" scenario specified? `cache.add` is documented as atomic across workers but the requirement isn't explicit. [Edge Case, Spec §Edge Cases]
- [x] CHK032 Is the "Flows delivery callback (RabbitMQ) replays a `delivered` event after the consumer crashed" scenario specified? Today the unique constraint on `external_message_id` would catch a re-create, but the requirement isn't stated. [Edge Case, Gap]
- [x] CHK033 Is the "PAUSED → APPROVED transition lands during the dedup window" scenario specified? The current edge case ("Concurrent broadcasts targeting the same paused template") covers paused, but not the un-pause race. [Edge Case, Spec §Edge Cases]
- [x] CHK034 Is the "Lambda returns the SAME `template` name for two distinct `current_state` values" race specified (e.g. operator misconfigures the rule engine and both `invoiced` and `shipped` resolve to `weni_order_invoiced`)? [Edge Case, Gap]
- [x] CHK035 Is the Direct Send Beta v3 error 132021 (template-name collision delivered asynchronously via webhook) acknowledged in the requirements? Could a Retail-side template name collide with a previously Direct-Send-auto-generated template in the same WABA? [Dependency, Gap]

## Non-Functional Requirements — Dedup Cache & Broker Failure Modes

- [x] CHK036 Is the dedup-cache backend's expected durability documented (Django cache backend → Redis vs. LocMemCache)? Without documentation, a Redis outage could silently downgrade to allow-all (per-process LocMem fallback). [NFR, Gap]
- [x] CHK037 Is the dedup-cache failure-mode requirement specified — when Redis is unreachable, MUST `cache.add` fail closed (skip dispatch) or fail open (allow possible duplicate)? [NFR, Gap, Plan §Stack]
- [x] CHK038 Is the broker delivery guarantee documented for the inbound status-update consumer (at-least-once expected; how to handle duplicates)? [NFR, Gap]

## Dependencies & Assumptions — Underlying Service Idempotency

- [x] CHK039 Is the assumption "the rule engine (AWS Lambda) returns DETERMINISTIC output for the same input" documented? Without it, a transient Lambda retry could produce different `template_variables` for the same event. [Assumption, Gap]
- [x] CHK040 Is the assumption "Flows' broadcast endpoint is idempotent given the same `broadcast_id`" documented as a dependency (or as a "we don't rely on Flows-side idempotency" stance)? [Assumption, Gap]
- [x] CHK041 Is the channel-app GET's read-once-at-assignment idempotency property (`Contract:integrations §5–§6`) consistent with the spec's "snapshot at assignment time" guarantee, including the corner case where the operator re-assigns mid-flight? [Consistency, Contract:integrations §5]

## Acceptance Criteria Quality — Measurable Idempotency Outcomes

- [x] CHK042 Can SC-005 ("for every dispatched broadcast, a record exists with the correct status, template name, and contact identifier") be objectively measured under retry / replay conditions, or only under happy-path conditions? [Measurability, Spec §SC-005]
- [x] CHK043 Can SC-002 ("100% of broadcast attempts that target a PAUSED or FLAGGED template result in a skipped dispatch") be objectively measured when the version's status flips mid-dedup-window? [Measurability, Spec §SC-002, Edge Case]
- [x] CHK044 Is "exactly once" measurable end-to-end (e.g. via a duplicate-detection metric on the Flows side or a Meta `auto_generated` template count) or only via Retail-internal counters? [Measurability, Gap]

## Ambiguities & Conflicts — Open Questions

- [x] CHK045 Does the spec or plan distinguish between "Retail does not retry on its own" (retry budget = 0) and "Retail tolerates external retries" (retry-safe)? Without the distinction, a reviewer can't tell whether Retail is meant to be Sisyphean or stoic. [Ambiguity, Gap]
- [x] CHK046 Is there a documented correlation identifier (e.g. an `event_id` or `trace_id` carried from VTEX webhook → Lambda → Retail → Flows → Meta) that lets operators stitch a single logical dispatch across logs and retry attempts? [Gap]
- [x] CHK047 Are any conflicts present between the spec's "operator can retry once Meta has the content (or recovers)" and `Contract:meta §4`'s "no retry policy in v1; library catalog is read at most once per template per assignment"? Both can be true if "once per ASSIGNMENT" applies (and a retry IS a new assignment), but the requirement should state this explicitly. [Conflict, Spec §Edge Cases, Contract:meta §4]

---

## Notes

- 47 items, organized by requirement-quality dimension (Completeness, Clarity, Consistency, Coverage, Edge Cases, NFR, Assumptions, Measurability, Ambiguities).
- Every item is phrased as a question about the WRITTEN REQUIREMENTS, never about the implementation.
- Markers used: `[Gap]`, `[Ambiguity]`, `[Conflict]`, `[Assumption]`, plus traceability references to `[Spec §X]`, `[Plan §X]`, `[Contract:gateway/meta/integrations §X]`, and `[Research D-X]` where the topic is already touched.
- An item that fails (i.e., the requirement is genuinely missing or ambiguous) should be resolved by amending the source document — `spec.md`, `plan.md`, `research.md`, or `contracts/*.md` — NOT by adding a code workaround.
- This checklist intentionally excludes performance / throughput tuning under retry storms (out of scope for the user's framing — separate checklist if needed).
- Cross-reference: existing `requirements.md` covers spec quality at the macro level; this checklist drills into idempotency specifically.

## Resolution Map (validation iteration 1 — 2026-05-21)

Every item above was resolved by amending the source documents
listed below. Reviewers can verify by reading the named section /
FR / Decision / Contract clause.

### Spec (`spec.md`)

- **Named Invariant — Exactly-Once Dispatch** + §Single logical broadcast + §Boundary + §Retry budget — CHK001, CHK002, CHK003, CHK045.
- **FR-003c** (failure-mode taxonomy: 200-empty / 4xx-5xx / malformed) — CHK020.
- **FR-003d** (atomic-rollback class + retry = new attempt + no partial-batch cache) — CHK016, CHK017.
- **FR-028 / FR-029 / FR-030 / FR-031** (duplicate trigger suppression, dedup window, different-state same-order, agent-resolution precedence) — CHK006, CHK007, CHK008, CHK009, CHK010, CHK024.
- **FR-032** (`BroadcastMessage` unique constraints with their conditions, restated as requirements) — CHK004, CHK021.
- **FR-033** (`BroadcastConversion` unique constraint `(project, order_id)` + last-touch attribution rule) — CHK005, CHK022.
- **FR-034** (`broadcasts_delivered` first-DELIVERED idempotency via `is_first_delivery` predicate) — CHK015.
- **FR-035** (inbound consumer retry-safety via `select_for_update` + lifecycle-rank guard) — CHK011, CHK032.
- **FR-036** (`MarkBroadcastConvertedUseCase` idempotency via `get_or_create`) — CHK012.
- **FR-037** (`RecordBroadcastSentUseCase` called-at-most-once contract) — CHK013.
- **FR-038** (Celery one-shot — `task.retry(...)` NOT used, `acks_late=False` early-ack, no DLX in v1; re-delivery absorbed by FR-035 inbound consumer idempotency + FR-028 trigger-side dedup + FR-036 `get_or_create`) — CHK014.
- **FR-039** (audit log shape catalogue — five refusal classes + one admission class, all disjoint) — CHK023, CHK025.
- **SC-002** amendment (measurability under status-flip races) — CHK043.
- **SC-005** amendment (measurability under retry/replay; 1:1 broadcast_id relation) — CHK042.
- **SC-009** (Retail-internal exactly-once measurable invariants) — CHK044.
- **Edge Cases** (two webhooks DIFFERENT state, concurrent same-tuple webhooks, official+custom agent match, Lambda same-template-name, Flows replay, PAUSED→APPROVED race, Direct Send 132021, Flows 5xx but reached Meta, dedup cache outage, `MarkBroadcastConverted` twice, re-assignment after `is_active=False`, two operators retrying) — CHK009, CHK010, CHK022, CHK027, CHK029, CHK030, CHK031, CHK032, CHK033, CHK034, CHK035, CHK037.
- **Assumptions** (retry budget = 0, Lambda determinism, Flows non-reliance, broker at-least-once, `broadcast_id` global uniqueness, multi-broadcast last-touch, manual re-dispatch, no new correlation identifier, dedup cache backend) — CHK022, CHK028, CHK036, CHK038, CHK039, CHK040, CHK045, CHK046.

### Plan (`plan.md`)

- **Constraints — Idempotency & retry safety** (canonical tuple, dedup backend, fail-closed, retry budget, broker semantics, Celery retry policy, no partial-batch caching, `BroadcastMessage` / `BroadcastConversion` keys, `broadcasts_delivered` semantics, audit log shape catalogue) — CHK014, CHK019, CHK036, CHK037, CHK038.

### Research (`research.md`)

- **Decision 15 — Idempotency & retry-safety model** (consolidated model, conflict resolution between operator retry and Meta §4, correlation-identifier stance, alternatives) — CHK018, CHK045, CHK046, CHK047.

### Contracts

- `contracts/messaging-gateway-payload.md` **§7 Idempotency** (retry budget, no-reliance on Flows idempotency, `broadcast_id` allocation, `external_message_id` uniqueness, status-callback replay, 132021 handling) — CHK026, CHK032, CHK035, CHK040.
- `contracts/meta-library-catalog.md` **§4** clarification ("per assignment ATTEMPT") + **§6** (partial-batch retries) + **§8** (deterministic failure return shape) — CHK018, CHK019, CHK047.
- `contracts/integrations-channel-app.md` **§5.1 Snapshot lifetime** + **§5.2 Failure semantics under retry** — CHK041.

### Items resolved by referring to existing requirements (no new text was needed beyond the FRs above)

Every CHK item above maps to at least one FR / Decision / Contract clause introduced in this iteration. No item required leaving a `[Gap]` open — the resolution map is complete.
