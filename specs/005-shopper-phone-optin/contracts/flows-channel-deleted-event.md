# Consumed event: Flows `channel.deleted`

**Producer**: Flows (`temba/channels/channel_events.py`, `temba/event_driven/publisher/channel_event_publisher.py`), published after commit of `Channel.release()` — the only production path that deactivates a channel — when `CHANNEL_EVENTS_PUBLISH_ENABLED=true` and `USE_EDA` are on. Best-effort delivery: a broker outage at enqueue time loses the event; publish failures retry up to 5 times; no outbox (verified 2026-10-09, research D-1).
**Consumer**: retail-setup `ChannelDeletedConsumer` (`retail/opt_in/consumers/channel_deleted_consumer.py`) → `HandleWhatsAppChannelDeletedUseCase` (FR-009, FR-009a, A9).

## Transport

| Item | Value |
|---|---|
| Exchange | `flows-channel-events.topic` (topic) |
| Routing key bound by retail | `channel.deleted.wac` (research D-1) |
| Queue | `retail.flows-channel-deleted` — durable quorum queue, delivery limit + dead-letter exchange, declared by infrastructure |
| Delivery | at least once |

## Envelope (weni-eda `Event.to_dict()`)

```json
{
  "event_id": "8a4c…",
  "event_type": "channel.deleted",
  "producer": "flows",
  "timestamp": "2026-10-07T20:15:03Z",
  "data": {
    "project_uuid": "0c1e…",
    "channel_uuid": "5b7f…",
    "channel_type": "WAC",
    "address": "123456789012345",
    "is_active": false,
    "occurred_at": "2026-10-07T20:15:02.913000+00:00",
    "whatsapp": {
      "phone_number": "+55 84 99999-0000",
      "phone_number_id": "123456789012345",
      "waba_id": "998877665544"
    }
  }
}
```

## Validation (constitution II) — tolerant reader

| Check | On failure |
|---|---|
| Body parses as JSON object | log `reason=malformed_body`, `ack` |
| `event_type == "channel.deleted"` | log `reason=unexpected_event_type`, `ack` |
| `data.project_uuid` is a UUID | log `reason=invalid_project_uuid`, `ack` |
| `data.channel_uuid` is a UUID | log `reason=invalid_channel_uuid`, `ack` |
| `data.channel_type ∈ {"WAC", "WA"}` | log `reason=not_whatsapp`, `ack` (defense in depth; the binding already filters) |

Unknown fields are ignored. `whatsapp.*`, `address`, `occurred_at` are informational (logged as opaque ids only; the phone number is never logged).

## Processing

1. `select_for_update` `OptInSettings` where `project__uuid = data.project_uuid` and `coupon_sender_channel_uuid = data.channel_uuid`.
2. No row → info log (`reason=project_not_found` when the project does not exist, else `reason=not_sender`), `ack`. Covers: non-sender numbers (US1-12a), duplicates (sender already cleared), unknown projects, out-of-order events after a reconnect (new channel UUID).
3. Row found and `coupon_enabled` → `coupon_enabled=False`, sender fields cleared, coupon-send deactivated (not deleted), storefront cache invalidated on commit, info log `action=coupon_disabled_sender_deleted`. No fallback to another number; nothing turns the coupon back on (FR-009, SC-013).
4. Database/infra failure → error log + Sentry (`correlation_id=event_id`), `nack` with requeue; the broker delivery limit bounds redelivery and dead-letters the message (constitution IV).

Processing is idempotent: a second delivery finds no matching sender.
