# Data Model: Shopping Assistant Opt-in — retail-setup orchestration

**Feature**: `005-shopper-phone-optin` | **Date**: 2026-10-07 | **Research**: [research.md](./research.md)

New Django app `retail.opt_in` (added to `INSTALLED_APPS`). All new models use Django's integer `BigAutoField` PK plus a public `uuid = UUIDField(default=uuid4, editable=False, unique=True)`, `created_at = auto_now_add`, `updated_at = auto_now` (constitution "Models").

One existing model changes: `retail.vtex.Cart` (one column, one partial unique index). No other existing model changes schema.

---

## 1. `OptInSettings` (new, `retail/opt_in/models.py`)

One row per project. Created lazily (`get_or_create`) by the first SA-state write or merchant save. **No row ⇒ SA not enabled, Opt-in off, coupon off** (FR-001, FR-002a).

| Field | Type | Null / default | Notes |
|---|---|---|---|
| `id` | `BigAutoField` | PK | internal |
| `uuid` | `UUIDField` | unique, default `uuid4` | public identifier |
| `project` | `OneToOneField(Project, on_delete=CASCADE, related_name="opt_in_settings")` | — | tenant key |
| `shopping_assistant_enabled` | `BooleanField` | `False` | written only by agentic-cx (FR-002a) |
| `shopping_assistant_recorded_at` | `DateTimeField` | null | last SA write that changed the value; null ⇒ never recorded (backfill diagnosis, A8) |
| `opt_in_enabled` | `BooleanField` | `False` | never turned on by retail on its own (FR-001) |
| `flows_opt_in_group_uuid` | `UUIDField` | null | set when the group is ensured (D-13) |
| `coupon_enabled` | `BooleanField` | `False` | |
| `coupon_discount_percent` | `DecimalField(max_digits=5, decimal_places=2)` | null | `0 < p ≤ 100` (A2a); shopper-facing copy |
| `coupon_code` | `CharField(max_length=100)` | `blank=True, default=""` | never exposed to the storefront |
| `coupon_sender_channel_uuid` | `UUIDField` | null | **Flows** channel UUID; match key for `channel.deleted` (FR-009a) |
| `coupon_sender_app_uuid` | `UUIDField` | null | Integrations `wpp-cloud` app UUID; template versions are per app |
| `coupon_sender_phone_number_id` | `CharField(max_length=64)` | `blank=True, default=""` | Meta phone number id, diagnosis only (FR-009a) |
| `coupon_sender_phone_number` | `CharField(max_length=32)` | `blank=True, default=""` | merchant business number, admin display |
| `coupon_send_integrated_agent` | `OneToOneField(IntegratedAgent, on_delete=PROTECT, null=True, related_name="opt_in_settings")` | null | the effective coupon-send automation (FR-005): the official coupon agent, or a custom agent whose `parent_agent_uuid = OPT_IN_COUPON_AGENT_UUID` (research D-3) |
| `coupon_status_confirmed_at` | `DateTimeField` | null | last successful status read from Integrations (D-4) |
| `created_at` / `updated_at` | `DateTimeField` | auto | |

**Constraints**

- `CheckConstraint(name="opt_in_settings_coupon_on_requires_fields")`:
  `Q(coupon_enabled=False) | (Q(coupon_discount_percent__isnull=False) & ~Q(coupon_code="") & Q(coupon_sender_channel_uuid__isnull=False) & Q(coupon_sender_app_uuid__isnull=False))` — FR-004a at the database level.
- `CheckConstraint(name="opt_in_settings_coupon_percent_range")`:
  `Q(coupon_discount_percent__isnull=True) | (Q(coupon_discount_percent__gt=0) & Q(coupon_discount_percent__lte=100))`.

**Indexes**

- The `OneToOneField` creates the unique index on `project_id` (hot path: storefront and merchant reads).
- `Index(fields=["coupon_sender_channel_uuid"], name="opt_in_settings_sender_idx")` — channel-deleted lookup. Queried together with `project__uuid`; selectivity comes from the channel UUID.
- Partial `Index(fields=["coupon_status_confirmed_at"], condition=Q(coupon_enabled=True), name="opt_in_settings_coupon_on_idx")` — periodic status refresh scans only coupon-on projects.

**Derived values (not stored)**

- `form_available = opt_in_enabled and shopping_assistant_enabled` (FR-011).
- `coupon_live` (D-4):
  ```
  coupon_enabled
  and coupon_sender_app_uuid is not None
  and latest_version_for_sender is not None and latest_version_for_sender.status == "APPROVED"
  and coupon_status_confirmed_at >= now - OPT_IN_COUPON_STATUS_MAX_STALENESS_SECONDS
  ```
  `latest_version_for_sender` = `Version.objects.filter(template=<coupon template>, integrations_app_uuid=coupon_sender_app_uuid).order_by("-created_at").first()`, where the coupon template is the active template of `coupon_send_integrated_agent` with `config["opt_in_role"] == "coupon"` (set on the official default template; required on custom agents — contracts/coupon-send-agent-lambda.md).
- `awaiting_approval = coupon_enabled and not coupon_live` (FR-010a: one indication for every not-live status).

**State rules**

| Event | `opt_in_enabled` | `coupon_enabled` | Sender fields | Coupon-send agent |
|---|---|---|---|---|
| Merchant: Opt-in on (SA enabled) | → `True` (after group + field ensured) | unchanged | unchanged | reconciler enqueued if coupon on |
| Merchant: Opt-in off | → `False` | unchanged (kept saved, US1-10) | unchanged | deactivated (sync) |
| Merchant: coupon on | unchanged | → `True` | set / validated at save time | reconciler enqueued |
| Merchant: coupon off | unchanged | → `False` | kept | deactivated (sync) |
| Merchant: sender change (coupon on) | unchanged | unchanged | → new sender; `coupon_status_confirmed_at` → null | reconciler enqueued (rebind) |
| agentic-cx: SA disabled | unchanged | unchanged | unchanged | deactivated (sync) |
| agentic-cx: SA enabled | unchanged | unchanged | unchanged | reconciler enqueued if Opt-in on and coupon on |
| EDA: sender channel deleted | unchanged | → `False` | cleared | deactivated (sync) |
| EDA: other channel deleted | unchanged | unchanged | unchanged | unchanged |

Every row change above deletes the storefront cache key on commit.

---

## 2. `OptInEligibility` (new)

At most one row per project × normalized session email (FR-012). No row ⇒ eligible. Anonymous shoppers never get a row (FR-017).

| Field | Type | Null / default | Notes |
|---|---|---|---|
| `id` | `BigAutoField` | PK | |
| `uuid` | `UUIDField` | unique | used as opaque reference in task args and Sentry |
| `project` | `ForeignKey(Project, on_delete=CASCADE, related_name="opt_in_eligibilities")` | — | |
| `email` | `CharField(max_length=254)` | — | `strip().lower()` before every read and write |
| `completed_at` | `DateTimeField` | null | no expiry while the row exists |
| `skip_until` | `DateTimeField` | null | server instant + 90 × 24 h |
| `name` | `CharField(max_length=128)` | `blank=True, default=""` | only after first membership |
| `phone` | `CharField(max_length=15)` | `blank=True, default=""` | E.164 digits, only after first membership |
| `created_at` / `updated_at` | `DateTimeField` | auto | |

**Constraints / indexes**

- `UniqueConstraint(fields=["project", "email"], name="opt_in_eligibility_unique_project_email")` — the only index; serves both the read and the upsert (architecture).

**Read rule** (FR-013): `completed_at` set → `completed` (+ name/phone when both non-empty); else `skip_until > now` → `skipped`; else `eligible`.

**Write rules**

| Operation | No row | Row with `completed_at` | Row with future `skip_until` | Row with past `skip_until` |
|---|---|---|---|---|
| Logged-in submit accepted (FR-020) | create with `completed_at=now` | unchanged | set `completed_at=now` | set `completed_at=now` |
| First membership resolved (FR-025) | — | set `name`, `phone` | — | — |
| Skip (FR-015) | create with `skip_until=now+90d` | unchanged | set `skip_until=now+90d` | set `skip_until=now+90d` |
| Promotion (FR-016) | create from browser state (D-16) | unchanged | unchanged | unchanged |

---

## 3. `OptInSubmit` (new)

One row per accepted submit (FR-026).

| Field | Type | Null / default | Notes |
|---|---|---|---|
| `id` | `BigAutoField` | PK | |
| `uuid` | `UUIDField` | unique | returned as `submit_id`; correlation reference |
| `project` | `ForeignKey(Project, on_delete=CASCADE, related_name="opt_in_submits")` | — | |
| `eligibility` | `ForeignKey(OptInEligibility, on_delete=SET_NULL, null=True, related_name="submits")` | null | set for logged-in submits; the email is never copied here |
| `whatsapp_identity` | `CharField(max_length=32)` | — | `whatsapp:<E.164 digits>` (FR-019) |
| `name` | `CharField(max_length=128)` | `blank=True, default=""` | cleared on `already_in_opt_in` and on retention (D-24) |
| `order_form_id` | `CharField(max_length=64)` | `blank=True, default=""` | job 3 input |
| `status` | `CharField(max_length=16, choices=SubmitStatus)` | `pending` | see transitions |
| `outcome` | `CharField(max_length=24, choices=SubmitOutcome)` | `blank=True, default=""` | `created`, `added`, `already_in_opt_in` |
| `contact_created_by_feature` | `BooleanField` | `False` | `True` only for `created` (FR-034) |
| `attempts` | `PositiveSmallIntegerField` | `0` | job 1 attempts, sync attempt included |
| `last_error_code` | `CharField(max_length=64)` | `blank=True, default=""` | e.g. `flows_timeout`, `flows_http_503`, `flows_http_400` |
| `resolved_at` | `DateTimeField` | null | |
| `coupon_status` | `CharField(max_length=24, choices=FollowUpStatus)` | `not_applicable` | job 2 |
| `coupon_sent_at` | `DateTimeField` | null | |
| `enrollment_status` | `CharField(max_length=32, choices=FollowUpStatus)` | `not_applicable` | job 3 |
| `enrolled_cart` | `ForeignKey(Cart, on_delete=SET_NULL, null=True, related_name="+")` | null | |
| `identifier_status` | `CharField(max_length=24, choices=FollowUpStatus)` | `not_applicable` | FR-034 |
| `created_at` / `updated_at` | `DateTimeField` | auto | |

**Indexes**

- `Index(fields=["project", "whatsapp_identity"], name="opt_in_submit_project_identity_idx")` — promotion match, identifier fill, diagnosis.
- `Index(fields=["status", "updated_at"], name="opt_in_submit_status_updated_idx")` — stale-pending sweeper, operator re-dispatch, retention cleanup.

**Enums** (`retail/opt_in/constants.py`, `TextChoices`)

- `SubmitStatus`: `pending`, `resolved`, `exhausted`.
- `SubmitOutcome`: `created`, `added`, `already_in_opt_in`.
- `FollowUpStatus`: `not_applicable`, `pending`, `sending`, `done`, `skipped_not_live`, `skipped_automation_inactive`, `skipped_no_order_form`, `skipped_order_form_unavailable`, `skipped_empty_cart`, `skipped_identifier_present`, `failed_retryable`, `failed_ambiguous`, `failed`.

**Status transitions** (compare-and-set on `status`; constitution IV)

```
             attempt resolves (created | added | already_in_opt_in)
 pending ───────────────────────────────────────────────────────────▶ resolved   (terminal)
    │  retryable failure, attempts < OPT_IN_SUBMIT_MAX_ATTEMPTS → stays pending, Celery retry
    │  retryable failure, attempts == max  OR  non-retryable 4xx
    ▼
 exhausted ── operator re-dispatch (management command, attempts := 0) ──▶ pending
```

On `pending → resolved`:

- `created` / `added` (first membership): set `coupon_status=pending` and `enrollment_status=pending` (or a `skipped_*` value when the precondition is already known false, e.g. no `order_form_id`); store name/phone on the eligibility row (logged in).
- `already_in_opt_in`: `coupon_status`, `enrollment_status` stay `not_applicable`; `name` cleared; eligibility row untouched beyond `completed_at`.

Follow-up transitions (each a CAS on its own column): `pending → sending → done | skipped_* | failed_retryable → sending … | failed_ambiguous | failed`.

---

## 4. `Cart` (existing, `retail/vtex/models.py`) — changed

| Change | Detail |
|---|---|
| New field | `opt_in = models.BooleanField(default=False)` — Opt-in attribution flag (FR-031). Phone of a flagged cart = existing `phone_number`. |
| New constraint | `UniqueConstraint(fields=["project", "order_form_id"], condition=Q(opt_in=True, status="created"), name="vtex_cart_unique_open_opt_in_order_form")` — at most one open flagged cart per order form (FR-032). |

**Migration** (`retail/vtex/migrations/0016_cart_opt_in.py`):

1. `AddField(opt_in, default=False)` — metadata-only on PostgreSQL ≥ 11.
2. `SeparateDatabaseAndState`: state = `AddConstraint(...)`; database = `RunSQL("CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS vtex_cart_unique_open_opt_in_order_form ON vtex_cart (project_id, order_form_id) WHERE opt_in AND status = 'created'", reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS vtex_cart_unique_open_opt_in_order_form")`, with `atomic = False`.

The existing `Index(fields=["order_form_id", "project"])` already serves the open-cart lookup by order form.

**Retention** (D-8): the daily `task_cleanup_old_carts` deletes carts with `opt_in=False` older than 15 days (unchanged rule) and carts with `opt_in=True` older than `OPT_IN_CART_RETENTION_DAYS` (30).

---

## 5. Existing models read or written (no schema change)

| Model | Use |
|---|---|
| `Project` | tenant; resolved from the token's `vtex_account` (storefront) or `project_uuid` (merchant/service) |
| `IntegratedAgent` | coupon-send automation (official or custom child linked by the existing `parent_agent_uuid`); `is_active`, `channel_uuid` and `contact_percentage` set by Opt-in; abandoned-cart agent only read (job 3) |
| `Agent` | new official coupon agent row with `lambda_arn`, created by the existing official-agent push flow; no schema change (`Agent` has no parent field — inheritance lives on `IntegratedAgent.parent_agent_uuid`) |
| `Template` / `Version` | designated coupon template (`Template.config["opt_in_role"] = "coupon"`, JSON key, no schema change) and its per-app versions; `Version.status` written only through `UpdateTemplateUseCase` |
| `IntegratedFeature` | read only (legacy abandoned-cart enablement check, job 3) |
| `BroadcastMessage` | written by the reused broadcast path for each coupon send |

---

## 6. Shared-cache keys (Redis via `django-redis`)

| Key | TTL | Purpose |
|---|---|---|
| `opt_in:storefront:{vtex_account}` | `OPT_IN_STOREFRONT_SETTINGS_CACHE_TTL_SECONDS` (60) | storefront settings payload (FR-011); deleted on commit of any settings/SA/disconnect change |
| `opt_in:submit_lock:{project_id}:{sha256(identity)}` | `OPT_IN_SUBMIT_LOCK_TTL_SECONDS` (60) | job 1 single flight per project × identity (FR-024) |
| `opt_in:flows_budget:{project_id}` | rolling hour | per-project token bucket for Flows contact calls, `OPT_IN_FLOWS_CONTACTS_BUDGET_PER_HOUR` (2000) below Flows' 2500/hour per org (research D-25) |
| `opt_in:coupon_reconcile_lock:{project_id}` | `OPT_IN_COUPON_RECONCILE_LOCK_TTL_SECONDS` (120) | reconciler single flight per project |
| `opt_in:flows_breaker:failures` / `opt_in:flows_breaker:open` | `OPT_IN_FLOWS_BREAKER_WINDOW_SECONDS` / `OPT_IN_FLOWS_BREAKER_OPEN_SECONDS` (30 / 30) | synchronous-attempt circuit breaker |

Identity is hashed in keys so no phone number is stored in Redis key names. Nothing in Redis is a system of record.
