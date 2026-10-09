# Quickstart: Shopping Assistant Opt-in (retail-setup)

How to run and validate the feature locally once implemented. Contracts: [contracts/](./contracts/). Data model: [data-model.md](./data-model.md).

## 1. Settings

Add to `.env` (defaults shown; every value is a named setting in `retail/settings.py`):

```bash
# Official coupon agent (pushed through the official-agent push flow, see §2)
OPT_IN_COUPON_AGENT_UUID=

# Dedicated Celery queues (FR-041)
OPT_IN_CONTACT_CELERY_QUEUE=opt-in-contact
OPT_IN_FOLLOWUP_CELERY_QUEUE=opt-in-followup

# Timeouts in seconds (FR-039)
OPT_IN_SUBMIT_SYNC_BUDGET_SECONDS=2.0
OPT_IN_FLOWS_TIMEOUT_SECONDS=5.0
OPT_IN_MERCHANT_FLOWS_TIMEOUT_SECONDS=5.0
OPT_IN_INTEGRATIONS_TIMEOUT_SECONDS=5.0
OPT_IN_VTEX_TIMEOUT_SECONDS=5.0

# Job 1 retry policy (FR-022, FR-023)
OPT_IN_SUBMIT_MAX_ATTEMPTS=10
OPT_IN_SUBMIT_RETRY_BACKOFF_BASE_SECONDS=5
OPT_IN_SUBMIT_RETRY_BACKOFF_MAX_SECONDS=900
OPT_IN_SUBMIT_STALE_AFTER_SECONDS=600
OPT_IN_SUBMIT_LOCK_TTL_SECONDS=60
OPT_IN_SUBMIT_SYNC_ATTEMPT_ENABLED=true

# Follow-up jobs (coupon, enrollment, reconciler)
OPT_IN_FOLLOWUP_MAX_ATTEMPTS=5
OPT_IN_FOLLOWUP_RETRY_BACKOFF_BASE_SECONDS=10
OPT_IN_FOLLOWUP_RETRY_BACKOFF_MAX_SECONDS=300
OPT_IN_COUPON_RECONCILE_LOCK_TTL_SECONDS=120

# Coupon status freshness (FR-005d); refresh + cache TTL must stay below the window
OPT_IN_COUPON_STATUS_MAX_STALENESS_SECONDS=900
OPT_IN_COUPON_STATUS_REFRESH_INTERVAL_SECONDS=300
OPT_IN_STOREFRONT_SETTINGS_CACHE_TTL_SECONDS=60

# Per-project budget for Flows contact calls (Flows throttles 2500/hour per org)
OPT_IN_FLOWS_CONTACTS_BUDGET_PER_HOUR=2000
OPT_IN_FLOWS_BUDGET_WAIT_SECONDS=60

# Synchronous-attempt circuit breaker (spike stability)
OPT_IN_FLOWS_BREAKER_FAILURE_THRESHOLD=20
OPT_IN_FLOWS_BREAKER_WINDOW_SECONDS=30
OPT_IN_FLOWS_BREAKER_OPEN_SECONDS=30

# Retention
OPT_IN_SUBMIT_RETENTION_DAYS=180
OPT_IN_CART_RETENTION_DAYS=30

# EDA consumer (channel.deleted)
USE_EDA=true
```

`python manage.py check` fails with `opt_in.E001` if `OPT_IN_COUPON_STATUS_REFRESH_INTERVAL_SECONDS + OPT_IN_STOREFRONT_SETTINGS_CACHE_TTL_SECONDS >= OPT_IN_COUPON_STATUS_MAX_STALENESS_SECONDS`.

## 2. Database and official agent

```bash
poetry run python manage.py migrate opt_in
poetry run python manage.py migrate vtex          # Cart.opt_in + concurrent partial unique index
# Official coupon agent: push its Lambda through the existing official-agent push flow
# (same process as order-status / abandoned-cart / back-in-stock), then set the Agent UUID:
#   OPT_IN_COUPON_AGENT_UUID=<pushed agent uuid>

# Rollout check of PR #590 (exact-parent filter, already on main; research F15), confirm existing custom agents:
#   SELECT DISTINCT parent_agent_uuid FROM agents_integratedagent WHERE parent_agent_uuid IS NOT NULL;
#   -> every value must equal ORDER_STATUS_AGENT_UUID
```

## 3. Processes

```bash
poetry run python manage.py runserver
./docker/entrypoint.sh celery-worker opt-in-contact
./docker/entrypoint.sh celery-worker opt-in-followup
./docker/entrypoint.sh celery-worker vtex-io-carts-events   # existing; abandonment timer of enrolled carts
./docker/entrypoint.sh celery-beat                           # status refresh, stale-submit sweeper, retention
poetry run python manage.py edaconsume                       # weni-eda consumers incl. retail.flows-channel-deleted
```

Broker setup for local EDA testing (production queues are declared by infrastructure):

```bash
rabbitmqadmin declare queue name=retail.flows-channel-deleted durable=true
rabbitmqadmin declare binding source=flows-channel-events.topic destination=retail.flows-channel-deleted routing_key=channel.deleted.wac
```

## 4. Smoke validation (happy paths)

Tokens: `$MERCHANT` (Keycloak, project contributor), `$SERVICE` (internal), `$SHOPPER` (retail JWT with `vtex_account` and `user_email`), `$ANON` (retail JWT with `vtex_account` only).

```bash
BASE=http://localhost:8000/api/v3/opt-in
P="Project-Uuid: $PROJECT_UUID"

# Defaults (US1-1)
curl -s -H "Authorization: Bearer $MERCHANT" -H "$P" $BASE/settings/

# Opt-in on is rejected until SA is recorded (US1-2, US1-12b) -> 409 shopping_assistant_not_enabled
curl -s -X PUT -H "Authorization: Bearer $MERCHANT" -H "$P" -H 'Content-Type: application/json' \
  -d '{"opt_in_enabled": true, "coupon": {"enabled": false}}' $BASE/settings/

# agentic-cx records SA enabled (FR-002a)
curl -s -X PUT -H "Authorization: Bearer $SERVICE" -H "$P" -H 'Content-Type: application/json' \
  -d '{"enabled": true}' $BASE/shopping-assistant/

# Opt-in on -> Flows group "Opt-in" ensured (US1-3)
curl -s -X PUT -H "Authorization: Bearer $MERCHANT" -H "$P" -H 'Content-Type: application/json' \
  -d '{"opt_in_enabled": true, "coupon": {"enabled": false}}' $BASE/settings/

# Coupon on with one connected number, no sender (US1-6) -> 200, sender auto-filled, awaiting_approval=true
curl -s -X PUT -H "Authorization: Bearer $MERCHANT" -H "$P" -H 'Content-Type: application/json' \
  -d '{"opt_in_enabled": true, "coupon": {"enabled": true, "discount_percent": "10", "code": "WELCOME10"}}' $BASE/settings/

# Storefront read: coupon reported as off until the template is approved (US1-13a)
curl -s -H "Authorization: Bearer $SHOPPER" $BASE/storefront/settings/

# Eligibility, skip, eligibility again (US3)
curl -s -H "Authorization: Bearer $SHOPPER" $BASE/storefront/eligibility/
curl -s -X POST -H "Authorization: Bearer $SHOPPER" $BASE/storefront/skip/

# Submit (US2) -> 200 first_membership | already_in_opt_in, or 202 pending
curl -s -X POST -H "Authorization: Bearer $SHOPPER" -H 'Content-Type: application/json' \
  -d '{"name": "Ana", "country_calling_code": "55", "national_number": "84999990000", "order_form_id": "abc123"}' \
  $BASE/storefront/submit/

# Flagged cart notification (US4)
curl -s -X POST -H "Authorization: Bearer $SHOPPER" -H 'Content-Type: application/json' \
  -d '{"cart_id": "abc123", "phone": "5584999990000", "name": "Ana", "opt_in": true}' \
  http://localhost:8000/vtex/abandoned-cart/api/notification/
```

Simulate a template approval locally (per-version webhook, existing route):

```bash
curl -s -X PATCH -H "Authorization: Bearer $SERVICE" -H 'Content-Type: application/json' \
  -d '{"version_uuid": "<coupon version uuid>", "status": "APPROVED"}' \
  http://localhost:8000/api/v3/templates/status/
```

The storefront read shows `coupon.live=true` within `OPT_IN_STOREFRONT_SETTINGS_CACHE_TTL_SECONDS`, provided the reconciler or the periodic refresh has confirmed the status within the staleness window.

## 5. Operations

```bash
# Re-dispatch exhausted submits after a Flows outage (FR-023)
poetry run python manage.py opt_in_redispatch_submits --project <uuid> --since 2026-11-28T00:00:00Z

# Re-dispatch ambiguous coupon-send failures (operator decision; may duplicate a send — research D-14)
poetry run python manage.py opt_in_redispatch_submits --project <uuid> --coupon
```

## 6. Tests and quality gates

```bash
poetry run coverage run manage.py test retail.opt_in retail.webhooks.vtex retail.agents retail.templates retail.clients retail.services
poetry run coverage report -m | tail -40
poetry run python contrib/compare_coverage.py
poetry run python manage.py makemigrations --check --dry-run
pre-commit run --all-files
```

Every Opt-in test class isolates the cache with `@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "<unique-per-class>"}})` and mocks Flows, Integrations, VTEX and the broker at the client/publisher boundary (constitution IX). Locks use `django.core.cache` (not raw `get_redis_connection`) so LocMemCache covers them in tests.
