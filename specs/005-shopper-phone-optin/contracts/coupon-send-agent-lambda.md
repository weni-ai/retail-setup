# Agent contract: official coupon-send agent (Lambda)

**Agent**: official active agent `OPT_IN_COUPON_AGENT_UUID` (`is_oficial=True`, `lambda_arn` set by the official-agent push flow).
**Invoked by**: retail-setup job 2 (`task_send_opt_in_coupon`) through `AgentWebhookUseCase.execute_from_task`, same pipeline as order-status, abandoned-cart and back-in-stock (research D-3, D-14).
**Contract version**: 1.0.0 — additive changes only within 1.x (constitution VIII). Custom agents based on this one (`IntegratedAgent.parent_agent_uuid = OPT_IN_COUPON_AGENT_UUID`) MUST honor the same contract.

## Invocation payload (`RequestData.payload`)

```json
{
  "event": "opt_in_first_membership",
  "submit_uuid": "a3f0…",
  "project_uuid": "0c1e…",
  "vtex_account": "store",
  "contact_urn": "whatsapp:5584999990000",
  "client_name": "Ana",
  "discount_percent": "10",
  "coupon_code": "WELCOME10",
  "coupon_template": "weni_opt_in_coupon_1759870000",
  "language": "pt_BR"
}
```

| Field | Meaning |
|---|---|
| `event` | Always `opt_in_first_membership` in v1 (job 2 runs only after outcome `created` or `added`) |
| `submit_uuid` | Opaque id of the submit; correlation and dedup reference |
| `contact_urn` | WhatsApp identity of the shopper (FR-019) |
| `client_name` | Name submitted on the form |
| `discount_percent`, `coupon_code` | Values stored in Opt-in settings **at send time** |
| `coupon_template` | `Template.name` of the effective agent's designated coupon template (`config["opt_in_role"] == "coupon"`) — the one whose approval retail checked |
| `language` | Template language of the designated template |

Credentials and ignored official rules are attached by `execute_from_task` as for every agent. The sender is not in the payload: the broadcast goes out through `IntegratedAgent.channel_uuid`, which retail keeps bound to the stored sender.

## Expected response (same shape as the other active agents)

Send:

```json
{
  "template": "weni_opt_in_coupon_1759870000",
  "contact_urn": "whatsapp:5584999990000",
  "template_variables": { "1": "Ana", "2": "10", "3": "WELCOME10" }
}
```

Do not send: a response without `template` (the pipeline returns `None`; retail records `skipped_not_dispatched` and never retries it).

## Rules for the official agent and its custom children

1. `template` MUST equal the payload's `coupon_template`. Retail computed liveness for that template only (BD-027); returning another template bypasses the "back in review" protection.
2. The Lambda MUST NOT send more than one message per invocation and MUST NOT call Flows directly — retail's broadcast path sends and records `BroadcastMessage`.
3. A custom child MUST keep exactly one active template with `config["opt_in_role"] == "coupon"`; without it the coupon is never live for that project.
4. The Lambda MUST NOT write the phone, name or coupon code to its own logs (FR-038).
5. Sampling: retail sets `contact_percentage=100` on the effective agent when activating it; the Lambda MUST NOT apply its own sampling to coupon sends (FR-028).
