# Contract change: abandoned-cart notification (`opt_in` flag)

**Route**: `POST /vtex/abandoned-cart/api/notification/` (existing, `AbandonedCartNotification`)
**Caller**: agentic-cx proxy (`/_v/abandoned-cart-notification`), retail JWT with `vtex_account`
**Change type**: additive, optional field — backward compatible within the current version (FR-031, FR-040, constitution VIII)

## Request body

| Field | Type | Required | Change |
|---|---|---|---|
| `cart_id` | string | yes | unchanged |
| `phone` | string | yes | unchanged. When `opt_in=true` this is the Opt-in phone held by the abandoned-cart script |
| `name` | string | yes | unchanged |
| `opt_in` | boolean | **no**, default `false` | **new** |

Unknown fields keep being ignored. A body without `opt_in` is processed exactly as today.

## Response

Unchanged: `200 {"message", "cart_uuid", "cart_id", "status"}`, `202` when the integration is not configured, `404` when the project is not found.

## Behavior with `opt_in`

| Project state | `opt_in` | Behavior |
|---|---|---|
| Abandoned-cart automation not enabled | any | existing `202` skip, flag not stored (US4-5) |
| Opt-in off | `true` | processed as today; flag not stored (FR-031, US4-4) |
| Opt-in off | `false`/absent | today's behavior, byte-for-byte |
| Opt-in on | `true`, no open cart for the order form | new cart with `opt_in=true`, `phone_number=<phone>` |
| Opt-in on | `true`, open unflagged cart for the order form | that cart becomes flagged, phone replaced by the Opt-in phone, abandonment task renewed — no second cart (FR-032, US4-2) |
| Opt-in on | any, open **flagged** cart for the order form | flag and Opt-in phone kept, abandonment task renewed (US4-3) |
| Opt-in on | `false`/absent, open unflagged cart(s) | today's per-phone behavior |

"Open" = `status="created"`. Recovery still waits for the existing abandonment window and dispatch (FR-033). Purchase handling never clears the flag.

## Upstream assumptions (FIIR)

- The agentic-cx proxy keeps its current skip when the abandoned-cart automation is inactive (A8). Retail does not rely on it: the automation check in `ProcessAbandonedCartNotificationUseCase` stays in place.
- The script sends `opt_in: true` only on `vtex:addToCart` / `orderFormUpdated` with ≥1 item. Retail does not rely on the trigger type either; idempotency per order form holds for any caller.
