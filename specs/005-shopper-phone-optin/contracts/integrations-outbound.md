# Outbound contract: retail-setup → Integrations engine

Calls are made by an `IntegrationsClient(request_timeout=OPT_IN_INTEGRATIONS_TIMEOUT_SECONDS, redact_payload=True)` instance and wrapped by services that never propagate raw exceptions (constitution I/III). Failure classes follow the Flows table (connection/timeout/5xx/429 retryable; other 4xx non-retryable).

## New: list WhatsApp Cloud channels of a project (research D-12)

`GET /api/v1/apptypes/wpp-cloud/channels/` — existing route in the integrations engine (`WhatsAppCloudChannelsView`), scoped by the `project_uuid` claim of the module JWT (same `JWTUsecase` as Flows module calls).

Response (array; `WhatsAppCloudChannelSerializer`):

```json
[
  {
    "app_uuid": "c3d1…",
    "channel_uuid": "5b7f…",
    "phone_number": "+55 84 99999-0000",
    "phone_number_id": "123456789012345",
    "waba_id": "998877665544",
    "name": "Loja X"
  }
]
```

Retail uses: `channel_uuid` (Flows channel = sender match key, FR-009a), `app_uuid` (template versions), `phone_number`, `phone_number_id`, `name`. Items with `channel_uuid = null` are not connected numbers and are ignored.

Used by: merchant read (FR-010a) and coupon-on save validation (FR-004, FR-004a/b).

## New: read a template's current status (A10, research D-4/D-5)

`GET /api/v1/apps/{app_uuid}/templates/?names=<version template_name>&page=1&page_size=1` with header `Project-Uuid` — existing route already used by `IntegrationsClient.fetch_templates_from_user`.

Retail reads from `results[0]`: `name`, `category`, and the translation whose `language` equals the local template language: `status`, `body`, `header`, `footer`, `buttons`.

| Result | Meaning for retail |
|---|---|
| `results` empty / 404 | version missing → repair (FR-005b) |
| translation present, content aligned with local metadata | status is authoritative: `APPROVED` → live candidate; anything else → not live, **no repair** |
| translation present, content not aligned | metadata misaligned → repair from local metadata (retail is the source of truth) |
| retryable failure | status unknown → retry; on exhaustion not live after the staleness window |

## Existing: create template + translation (unchanged)

`POST /api/v1/apps/{app_uuid}/templates/` and `POST /api/v1/apps/{app_uuid}/templates/{uuid}/translations/` via `task_create_template` — used by the repair path with the sender's `app_uuid`.

## Existing inbound: per-version status webhook (unchanged)

Integrations → `PATCH /api/v3/templates/status/` `{"version_uuid", "status"}` → `UpdateTemplateUseCase`. Primary near-real-time source of `Version.status` for liveness.
