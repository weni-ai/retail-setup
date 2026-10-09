# Outbound contract: retail-setup → Flows

All calls use the public v2 routes with the module JWT (`FlowsClient._module_jwt_headers(project_uuid)`), are made by a `FlowsClient(request_timeout=…, redact_payload=True)` instance (research D-7, D-18) and are wrapped by `FlowsContactService`, which classifies failures:

| Failure | Class | Mapped to |
|---|---|---|
| connection error, timeout (`CustomAPIException.status_code is None`) | retryable | `FlowsTransientError` |
| HTTP 5xx | retryable | `FlowsTransientError` |
| HTTP 429 (throttle, research D-25) | retryable, countdown `max(backoff, Retry-After)` | `FlowsThrottledError` |
| HTTP 400 `{"urns": ["URN belongs to another contact: <urn>"]}` on create | race | `FlowsContactUrnAlreadyExistsError` (existing) → re-lookup |
| HTTP 400 `{"fields": ["Invalid contact field key: identifier"]}` | non-retryable (config) | `FlowsRejectedError(status_code)` — field missing, ensure it |
| other HTTP 4xx | non-retryable | `FlowsRejectedError(status_code)` |

No failure is ever mapped to "already in Opt-in" (FR-022).

Behaviors below were verified against the Flows code on 2026-10-09 (branch `feature/publish-channel-deleted-events`), research D-6a, D-9a, D-13, D-25.

## Operations

| Operation | Request | Verified behavior | Used for |
|---|---|---|---|
| Find group | `GET /api/v2/groups.json?project=<p>&name=Opt-in` | `name__iexact`, not partial | ensure group (FR-003) |
| Create group | `POST /api/v2/groups.json?project=<p>` `{"name": "Opt-in"}` | — | ensure group |
| Find contact field | `GET /api/v2/fields.json?project=<p>&key=identifier` | — | ensure field on Opt-in enable |
| Create contact field | `POST /api/v2/fields.json?project=<p>` `{"label": "Identifier", "value_type": "text"}` | key derived from label → `identifier`; not reserved | ensure field on Opt-in enable |
| Lookup contact | `GET /api/v2/contacts.json?project=<p>&urn=whatsapp:<digits>` | exact identity, no 9th-digit variant; paginated `results[]` with `uuid`, `groups[] {uuid, name}`, `fields` (every org field, `null` when unset) | job 1 every attempt (exact canonical identity, D-6a); identifier fill |
| Create contact | `POST /api/v2/contacts.json?project=<p>` `{"name", "urns": ["whatsapp:<canonical digits>"], "groups": ["<opt-in group uuid>"], "fields": {"identifier": "<email or empty>"}}` | exact identity check; `groups` accepts UUID or name | outcome `created` |
| Add to group | `POST /api/v2/contact_actions.json?project=<p>` `{"contacts": ["<contact uuid>"], "action": "add", "group": "<opt-in group uuid>"}` | `204`, no membership check; name/URNs/fields untouched | outcome `added` (targets the contact found by the lookup) |
| Update contact fields | `POST /api/v2/contacts.json?project=<p>&uuid=<contact uuid>` `{"fields": {"identifier": "<normalized email>"}}` | body with only `fields` keeps name, URNs, groups; `404` when the contact is gone | identifier fill (FR-034), after a fresh lookup shows the field empty |
| Template broadcast | `POST /api/v2/internals/whatsapp_broadcasts` (internal OIDC) | — | job 2 through the agent pipeline, `channel` = sender Flows channel |

Do **not** use `POST /api/v2/contacts.json?urn=…` for writes: it is an upsert that creates a contact when none matches and, with `verify_ninth_digit`, may update the other BR form; any `groups` in that body replaces static groups.

All operations already exist in the Flows public v2 API; retail asks Flows for **no new behavior**. Flows' role stays limited to notifying channel deactivation (`channel.deleted`), sending messages and the inherited Opt-in group protection below (decided 2026-10-08).

## Throttle (research D-25)

Per org, shared by every module-JWT caller: `contacts.json` 2500/hour (`v2.contacts`); `groups.json`, `fields.json`, `contact_actions.json` 2500/hour (`v2`). Retail keeps its own per-project budget below that (`OPT_IN_FLOWS_CONTACTS_BUDGET_PER_HOUR`) and treats `429` as retryable.

## Existing Flows behaviors retail relies on (no change requested)

- URN uniqueness per org (`ContactURN` unique with org) — protection against duplicate contacts on retries for the same identity form.
- Lookup by URN returns the contact's groups — retail decides "already in Opt-in" from it, so Flows does not need a dedicated error payload.
- Adding an existing contact to a group does not change its name, URNs or fields — retail never "rejects because the number exists".

## Inherited Flows responsibility (kept)

Per the architecture (pinned `001-new-client-phone-optin-v1.5`, "Flows contact contract") and BD-017, Flows protects the **Opt-in** group against delete and rename. Retail cannot enforce it from its side and relies on it; confirmed 2026-10-08 as a Flows safety layer, so there is no divergence.

## Timeouts

`OPT_IN_SUBMIT_SYNC_BUDGET_SECONDS` (in-request attempt, per call `min(OPT_IN_FLOWS_TIMEOUT_SECONDS, remaining)`), `OPT_IN_FLOWS_TIMEOUT_SECONDS` (background), `OPT_IN_MERCHANT_FLOWS_TIMEOUT_SECONDS` (merchant save).
