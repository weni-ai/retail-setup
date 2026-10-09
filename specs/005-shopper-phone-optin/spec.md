## Inheritance from Product Spec
- Product Spec: New client phone capture opt-in — https://github.com/weni-ai/vtex-cx-experience-specs/tree/main/specs/001-new-client-phone-optin
- Pinned version: 001-new-client-phone-optin-v1.5 (52d927b)
- Architecture doc: https://github.com/weni-ai/vtex-cx-experience-specs/blob/001-new-client-phone-optin-v1.5/specs/001-new-client-phone-optin/architecture.md (001-new-client-phone-optin-v1.5, 52d927b)
- Inherited binding decisions: BD-001 – BD-027
- Scope of this spec: retail-setup
- Divergences: none

# Feature Specification: Shopping Assistant Opt-in — retail-setup orchestration

**Feature Branch**: `005-shopper-phone-optin`

**Created**: 2026-10-01

**Status**: Draft

**Input**: User description: "Inherit product spec `001-new-client-phone-optin` (pinned `468ed22`) and its architecture document (pinned `fdcc31e`), binding decisions BD-001 – BD-026, scoped to the retail-setup slice, with no divergences."

## Inheritance history

| Date | Product spec pin | Architecture pin | Inherited change that affects this slice |
|---|---|---|---|
| 2026-10-01 | `468ed22` (contract v1.3) | `fdcc31e` | Initial inheritance |
| 2026-10-02 | `001-new-client-phone-optin-v1.4` (`726ade0`) | `001-new-client-phone-optin-v1.4` (`726ade0`) | Coupon sender number for accounts with 2+ connected WhatsApp numbers; coupon toggle available with at least one connected number; coupon saves only with discount percent, code and (with 2+ numbers) sender; sender disconnect turns the coupon off with no fallback; sender change applies to later sends only; going from one to 2+ numbers keeps the sender (product FR-003i, FR-003j, FR-028, BD-001, BD-002c, BD-016, BD-019, SC-016 – SC-018) |
| 2026-10-05 | `001-new-client-phone-optin-v1.5` (`52d927b`) | `001-new-client-phone-optin-v1.5` (`52d927b`) | Coupon template approval gate: the coupon is **live** only when it is on, its sender is connected and the coupon template is approved by Meta for that sender; in any other status (pending, rejected, paused, disabled, back in review, not approved for a new sender, unknown) the storefront shows the version without coupon, nothing is sent, the coupon stays on and saved, and the admin coupon section shows a warning; the coupon goes live again with no merchant action, within 15 minutes; no retroactive send for shoppers who completed while it was not live (product FR-003d, FR-003k, FR-013, FR-028, NFR-008, BD-027, SC-019, SC-020). Supersedes the 2026-10-02 clarification that held coupons for up to 48 hours |

## Clarifications

### Session 2026-10-01

- Q: Retail-setup has no record of whether Shopping Assistant is enabled. Which system is the source of truth for the enable gate and for reacting to Shopping Assistant being turned off? → A: **Retail-setup owns the flag.** Agentic-cx writes it to retail-setup whenever the merchant turns Shopping Assistant on or off; retail-setup uses it for the Opt-in enable gate and to deactivate/reactivate coupon-send.
- Q: Retail-setup receives no event when a WhatsApp number is disconnected. How does it learn about the disconnect so the coupon turns off? → A: **Upstream disconnect event only.** Retail-setup consumes a disconnect event published by the channel owner and turns the coupon off when it arrives. *(Corrected on 2026-10-07: the channel owner is **Flows**, not Integrations/Connect. Flows publishes `channel.deleted` on every channel deactivation; Integrations only consumes it to delete its own app and does not notify anyone else. See A9.)*
- Q: What peak load must the slice sustain? → A: **10,000 transactions per minute as a baseline, not a ceiling.** Special dates such as Black Friday can exceed the usual monitoring curve, so the design must favor stability under spikes rather than a fixed number.

### Session 2026-10-02

- Q: When the merchant turns the coupon on and the coupon-send automation is inactive, what must retail-setup verify before reactivating it, and what if something is wrong? → A: The coupon can be turned on even while the automation is inactive. Before reactivating it, retail-setup checks through Integrations that the automation's template and its current version still exist and are approved, and that the template metadata is aligned between retail-setup and Integrations. If everything holds, it reactivates. If anything does not, retail-setup repairs it (for example, recreates the missing version) and then reactivates. The merchant never gets an error from this check. *(Refined on 2026-10-05: a version that exists but is not approved is not repaired; it only keeps the coupon not live.)*
- Q: While a recreated template version waits for Meta approval, what happens to coupons for shoppers who join the group in that window? → A: *(Superseded on 2026-10-05 by product v1.5, BD-027.)* Originally answered "hold them for up to 48 hours". Product v1.5 forbids a later send to shoppers who completed while the coupon was not live, so nothing is held: those shoppers saw the version without coupon and receive no coupon.
- Q: When the readiness check finds the template metadata misaligned between retail-setup and Integrations, which side wins? → A: **Retail-setup is the source of truth.** Retail-setup creates a new version in Integrations from its local metadata (including any merchant edit made in Automations); until that version is approved, the coupon is not live (BD-027).

### Session 2026-10-05

- Q: Should the repair recreate a template version that exists in Integrations but is not approved (pending, rejected, paused, disabled)? → A: **No.** The repair recreates only when the template or its current version is missing in Integrations, or when the metadata is misaligned. A version that exists but is not approved is left as is: the coupon is simply not live until Meta approves it or the merchant edits the message in Automations.

## Slice boundary

The architecture document assigns retail-setup the **orchestrator** role. This spec covers only what retail-setup owns; shopper-facing UX, session validation, contact storage and the storefront script belong to sibling repositories and are listed as dependencies.

| System | Owns (per architecture) | In this spec |
|---|---|---|
| **retail-setup** | Eligibility record, merchant Opt-in settings, coupon-send automation, VTEX account → project resolution, every call to Flows, Opt-in flag on abandoned carts | **Yes** |
| agentic-cx | Proves the caller (`vtex_session` / merchant session), mints the retail token, forwards. Stores no Opt-in state | Dependency |
| webchat-react / webchat-service | Teaser, form, display algorithm, anonymous browser memory, `weni:opt-in-confirmed` event | Dependency |
| flows | WhatsApp contacts, the **Opt-in** group, delete/rename protection of that group; source of truth for channels, publishing `channel.deleted` on every channel deactivation | Dependency |
| agentic-cx-script (abandoned-cart script) | Stores the confirmed pair, sends `opt_in: true` on qualifying notifications | Dependency |

### Binding decision responsibility map

The binding decisions are inherited unchanged. This table only states which ones retail-setup enforces; it does not reinterpret them.

| Binding decision | retail-setup responsibility |
|---|---|
| BD-001, BD-016 | Enforce the enable gate server-side (Opt-in off by default, enable only while Shopping Assistant is enabled, coupon only while at least one WhatsApp number is connected); react to Shopping Assistant off and to the coupon sender number being disconnected |
| BD-002b, BD-007, BD-015, BD-019, BD-002c | Store coupon on/off, percent, code and sender number; reject coupon saves missing a required field; create/activate/deactivate the coupon-send automation bound to the sender number; never create or touch the abandoned-cart automation |
| BD-002e | Re-validate country calling code + national number on the server and normalize it into the WhatsApp identity; never check WhatsApp existence |
| BD-027 | Decide whether the coupon is **live** (on, sender connected, template approved for the sender); expose it to the storefront read (coupon or no-coupon copy) and to the merchant read (approval warning); check approval again at send time; treat an unknown status as not approved |
| BD-003, BD-020, BD-005 | Persist the Opt-in flag on the cart, use the Opt-in phone on flagged registers, enroll the current cart at first membership, reuse the existing dispatch |
| BD-004, BD-004b, BD-018, BD-022, BD-023, BD-025 | Own the authenticated eligibility record keyed by project × normalized session email, compute `skip_until`, promote browser records on login, never treat a known phone as completion |
| BD-014, BD-017, BD-026 | Run post-submit orchestration with the three Flows outcomes plus the no-response path; never mutate a contact already in **Opt-in**; never let a Flows failure become a shopper-facing error |
| BD-012, BD-013, BD-024 | Results screens are deferred (architecture, "Attribution for a later dashboard"); retail-setup only keeps the data those screens will need |
| BD-002, BD-002a, BD-002d, BD-006, BD-008, BD-009 – BD-011, BD-021 | Not enforced by retail-setup (widget behavior, or out of v1 scope) |

## Peak load *(mandatory — constitution V)*

- **Declared peak**: at least **10,000 transactions per minute** across the Opt-in storefront traffic below. This is a floor, not a ceiling: special dates (Black Friday and similar) are expected to go beyond the usual monitoring curve, and the slice MUST stay stable when they do.
- **Stability over a fixed number**: under a spike above the declared peak, the slice MUST degrade without shopper-facing failures — settings and eligibility reads keep answering, valid submits are accepted and resolved later instead of being rejected, and slow or failing dependencies (Flows, VTEX, automation sends) never hold storefront requests beyond their bounded budget.

Traffic that the peak covers:

- **Storefront settings read**: up to one per visit, anonymous or logged in. The hottest path.
- **Eligibility read**: at most one per logged-in visit plus one per login. No shared cache in front of it (architecture), so every read reaches the system of record.
- **Skip write**: at most one per logged-in skip.
- **Submit**: at most one per form-shown session that passes local validation, each followed by background Flows, coupon and enrollment work.
- **Opt-in-flagged cart notifications**: a subset of the existing abandoned-cart notification traffic (`vtex:addToCart` and `orderFormUpdated` only).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Merchant turns Opt-in and the coupon on and off under the server-side gates (Priority: P1)

The merchant saves Opt-in settings from the admin screen in agentic-cx; the proxy forwards the save to retail-setup. Retail-setup stores Opt-in on/off, coupon on/off, discount percent, coupon code and the coupon sender number for the project, and applies the enable gates and required-field checks itself — the screen is not the only place the check runs. With exactly one connected WhatsApp number, that number is the sender; with two or more, the merchant must pick one. Turning Opt-in on makes sure the Flows group named **Opt-in** exists. Turning the coupon on creates or activates the coupon-send automation seeded with the platform default template and bound to the sender number. Every "off" path deactivates, never deletes, and the abandoned-cart automation is never created, activated, or deactivated by Opt-in.

**Why this priority**: Every shopper flow depends on these settings, and the enable gates are binding decisions (BD-001, BD-016) that the server must enforce on its own.

**Independent Test**: For a project with Shopping Assistant disabled, try to save Opt-in on and confirm it is rejected and nothing changes. Enable Shopping Assistant and save Opt-in on with no WhatsApp channel and no abandoned-cart automation: the save succeeds, the **Opt-in** group exists in Flows with no contacts, and no automation was created. Try to turn the coupon on and confirm it is rejected. Connect one WhatsApp number, turn the coupon on with a code that matches no VTEX promotion and no sender: the save succeeds, that number is the sender, and the coupon-send automation is active. Connect a second number and confirm the sender and the coupon are unchanged. Disconnect the sender: the coupon turns off and does not fall back to the other number. Turn Opt-in off: the coupon-send automation is inactive (still exists), the group is unchanged, and the abandoned-cart automation is exactly as it was.

**Acceptance Scenarios**:

1. **Given** a project that has never saved Opt-in settings (new onboarding or a project already live in production), **When** settings are read, **Then** Opt-in is off and the coupon is off.
2. **Given** Shopping Assistant is not enabled for the project, **When** the merchant saves Opt-in on, **Then** the save is rejected with a stable error code and the stored settings are unchanged.
3. **Given** Shopping Assistant is enabled, no abandoned-cart automation is active and no WhatsApp number is connected, **When** the merchant saves Opt-in on, **Then** the save succeeds, no abandoned-cart automation is created or activated, and the Flows group named **Opt-in** exists for the project.
4. **Given** the group named **Opt-in** already exists in the project's Flows org, **When** Opt-in is turned on again, **Then** the existing group is reused and no second group is created.
5. **Given** no WhatsApp number is connected, **When** the merchant saves the coupon on, **Then** the save is rejected with a stable error code and the coupon stays off.
6. **Given** exactly one WhatsApp number is connected, **When** the merchant saves the coupon on with a percent and a code and no sender, **Then** the save succeeds even if the code does not resolve to a VTEX promotion and even if the percent differs from the promotion's discount, that number is stored as the sender, and the coupon-send automation exists, is active with the platform default template, and is bound to that number.
6b. **Given** any number of connected WhatsApp numbers, **When** the merchant saves the coupon on without a discount percent or without a code, **Then** the save is rejected with a field-level error, nothing is stored, and coupon-send is not activated.
6c. **Given** two or more WhatsApp numbers are connected, **When** the merchant saves the coupon on without a sender, **Then** the save is rejected with a field-level error on the sender, nothing is stored, and coupon-send is not activated; retail-setup does not pick a number on its own.
6d. **Given** two or more WhatsApp numbers are connected, **When** the merchant saves the coupon on with a sender that is one of them, **Then** the save succeeds and coupon-send is bound to that number. **When** the sender is not one of the project's connected numbers, **Then** the save is rejected with a field-level error.
6e. **Given** the coupon is on, **When** the merchant changes the sender to another connected number, **Then** coupon-send is rebound to the new number, later sends use it, and no coupon already sent is sent again.
6f. **Given** the coupon is on with one connected number as sender, **When** a second number is connected, **Then** the sender and the coupon stay as they were.
7. **Given** the coupon-send automation already exists (active or inactive), **When** the coupon is turned on again, **Then** retail-setup runs the readiness check, the existing automation is reactivated with its current message (including any merchant edit made in Automations), and no second automation is created.
7a. **Given** the coupon-send automation is inactive and its current template version no longer exists in Integrations (or its metadata differs from retail-setup), **When** the merchant turns the coupon on, **Then** the save succeeds without an error, retail-setup recreates or realigns what is missing, and the automation is reactivated; the coupon becomes live once the recreated version is approved.
7b. **Given** the coupon-send automation is inactive and its current version exists in Integrations but is pending, rejected, paused or disabled, **When** the merchant turns the coupon on, **Then** the save succeeds without an error, no new version is created, the automation is reactivated, and the coupon stays not live (with the awaiting-approval warning) until the version is approved.
8. **Given** the coupon is on, **When** the merchant turns the coupon off, **Then** the coupon-send automation becomes inactive and is not deleted.
9. **Given** Opt-in is on, **When** the merchant turns Opt-in off, **Then** coupon-send becomes inactive, the **Opt-in** group and its contacts are untouched, and the abandoned-cart automation keeps the state the merchant left it in.
10. **Given** Opt-in was turned off with the coupon still on, **When** the merchant turns Opt-in on again while Shopping Assistant is enabled, **Then** coupon-send is reactivated, bound to the same sender.
11. **Given** Opt-in and coupon are on, **When** agentic-cx records Shopping Assistant as disabled, **Then** Opt-in stays on, the coupon setting stays as saved, coupon-send becomes inactive, and the storefront settings read reports the form as not available.
12. **Given** the coupon is on, **When** the disconnect event for the coupon sender number arrives, **Then** the coupon turns off and coupon-send becomes inactive (not deleted), even if other numbers stay connected; retail-setup does not switch to another number. **When** WhatsApp is reconnected, **Then** the coupon stays off until the merchant turns it on again (selecting a sender again when two or more numbers are connected).
12a. **Given** the coupon is on, **When** the disconnect event is for a connected number that is not the sender, **Then** the coupon, the sender and coupon-send are unchanged.
12b. **Given** a project for which agentic-cx has never recorded a Shopping Assistant state, **When** the merchant saves Opt-in on, **Then** the save is rejected as if Shopping Assistant were not enabled.
13. **Given** Opt-in is on, **When** the storefront reads the Opt-in settings, **Then** it receives whether the form is available, whether the coupon is live and (only while live) the percent, and never the coupon code, the sender number, or the template status.
13a. **Given** the coupon is on but its template is pending, rejected, paused, disabled, or back in review for the sender, **When** the storefront reads the Opt-in settings, **Then** the coupon is reported exactly as if it were off. **When** the template becomes approved, **Then** within 15 minutes the read reports the coupon as live, with no merchant action.
13b. **Given** the coupon is on but not live because of the template status, **When** the merchant reads the settings, **Then** they report the coupon as on, saved and editable, plus an awaiting-approval indication for the coupon section warning; saving again is not blocked.
14. **Given** the merchant opens Opt-in settings, **When** the settings are read for the admin screen, **Then** they include the project's connected WhatsApp numbers and the current sender, so the screen can hide the selector with one number, show it without a pre-selection with two or more, and disable the toggle with none.

---

### User Story 2 - Shopper submit is orchestrated against Flows without ever failing the shopper (Priority: P1)

After the widget has already shown success, agentic-cx forwards the submit (name, country calling code, national number, the session email when logged in, and the `orderFormId` when the page has one). Retail-setup re-validates the input, records completion for a logged-in shopper as soon as it accepts the payload, and runs the three jobs from the post-submit orchestration: contact (job 1), coupon (job 2) and abandoned-cart register (job 3). Job 1 has exactly three Flows outcomes — new number, existing contact not in **Opt-in**, already in **Opt-in** — plus the no-response case, which retail-setup retries until one of the three is known. Coupon-send and cart enrollment run only after a first membership.

**Why this priority**: This is how a shopper joins the audience. A wrong outcome here either sends a coupon or recovery message to someone who did not just join (a third party's number already in the group) or drops a real new contact.

**Independent Test**: With Flows mocked at the client boundary, submit a new number from a logged-in session with the coupon on (sender connected), abandoned cart enabled and an order form that has one item. Verify: one contact created with name, WhatsApp identity and the session email as identifier, membership in **Opt-in**, one coupon send, one flagged cart enrollment, the eligibility row with `completed_at`, name and phone, and a response reporting first membership. Repeat with a number already in **Opt-in** and verify no Flows write, no coupon, no enrollment, `completed_at` written without name and phone, and a response reporting already-in-Opt-in. Repeat with Flows timing out on the first attempt and succeeding on the retry and verify the jobs run once after the retry resolves.

**Acceptance Scenarios**:

1. **Given** a valid submit from a logged-in shopper, **When** retail-setup accepts the payload, **Then** `completed_at` is written on the eligibility row for project × normalized email before any Flows call completes.
2. **Given** a number with no WhatsApp contact in the project's Flows org, **When** job 1 runs, **Then** a contact is created with the submitted name, the WhatsApp identity and an identifier equal to the session email (empty when anonymous), it is added to **Opt-in**, and the outcome is first membership.
3. **Given** a WhatsApp contact that exists and is not in **Opt-in**, **When** job 1 runs, **Then** the contact is added to **Opt-in**, its identifier, name and phone are not changed, no second contact is created, and the outcome is first membership.
4. **Given** a WhatsApp contact already in **Opt-in**, **When** job 1 runs, **Then** no Flows write happens, no name or phone is stored on the eligibility row, coupon-send does not run, the cart is not enrolled, and the outcome is already-in-Opt-in.
5. **Given** a first membership by a logged-in shopper, **When** job 1 completes, **Then** the submitted name and phone are stored on the eligibility row.
6. **Given** a first membership, the coupon live and coupon-send active at that moment, **When** job 1 completes, **Then** the coupon template is sent once through the coupon-send automation, from the sender number stored at that moment, without waiting for a cart.
7. **Given** a first membership but the coupon off (including because the sender was disconnected), not live because the template is not approved, or coupon-send inactive at that moment, **When** job 1 completes, **Then** no coupon is sent, and no coupon is sent later when the coupon is turned on.
8. **Given** a first membership, the abandoned-cart automation enabled at that moment, and a submitted `orderFormId` whose cart has at least one item, **When** job 1 completes, **Then** that cart is enrolled immediately with the submitted phone and the Opt-in flag, through the same processing the abandoned-cart notification uses.
9. **Given** a first membership but the abandoned-cart automation not enabled, or no `orderFormId`, or a cart with zero items, **When** job 1 completes, **Then** no cart is enrolled and nothing is sent to be ignored later.
10. **Given** Flows does not answer (timeout or dropped call, no error payload), **When** job 1 runs, **Then** the outcome is not treated as already-in-Opt-in; retail-setup retries with a bounded policy until the outcome is create, add, or already-in-Opt-in, and runs jobs 2 and 3 only if the resolved outcome is a first membership.
11. **Given** a retry that finds the contact already in **Opt-in**, **When** it resolves, **Then** it follows the already-in-Opt-in outcome and does not create a second contact.
12. **Given** the outcome is known within the request budget, **When** retail-setup responds, **Then** the response reports first membership (with the confirmed name and phone) or already-in-Opt-in. **Given** it is not known yet, **Then** the response reports the submit as pending and the resolution continues in the background.
13. **Given** coupon-send or cart enrollment fails after a first membership, **When** the failure happens, **Then** the eligibility row keeps `completed_at` (and name and phone), and the failure is logged and recoverable.
14. **Given** a submit whose name is empty, whose country calling code is unknown, or whose national number is not valid for that country, **When** retail-setup validates it, **Then** it is rejected with a field error, nothing is written, and no Flows call is made.

---

### User Story 3 - Authenticated eligibility is read, skipped and promoted per project and email (Priority: P1)

For a logged-in shopper, the widget asks (through agentic-cx) whether the Opt-in form may be shown. Retail-setup answers from the eligibility record for project × normalized session email: eligible (no row), completed (with name and phone when the row has them), or skipped until a given instant. A "Not now" or teaser close from a logged-in shopper writes `skip_until`. On login, when the browser already holds `complete` or `skip_until` and the server row is empty, retail-setup promotes the browser record. A known VTEX, profile or cart phone never makes a shopper ineligible.

**Why this priority**: Cross-browser suppression for logged-in shoppers (BD-004b, BD-023) only works if the server record is correct and read on every visit.

**Independent Test**: For email `Shopper@Store.com` on project A, read eligibility and get eligible. Write a skip and read again: skipped, with `skip_until` exactly 90 × 24 hours after the server's skip instant. Read with `shopper@store.com ` (different case, trailing space) and get the same row. Read the same email on project B and get eligible. Promote a browser `complete` with a phone that reached first membership on project A and confirm the row stores the server-recorded name and phone.

**Acceptance Scenarios**:

1. **Given** no eligibility row for project × normalized email, **When** eligibility is read, **Then** the answer is eligible, whether or not the shopper has a phone on the VTEX profile, the cart, or a Flows contact.
2. **Given** a row with `completed_at` and a name and phone, **When** eligibility is read, **Then** the answer is completed with that name and phone.
3. **Given** a row with `completed_at` and no name and phone (already-in-Opt-in submit, or a completion whose Flows outcome is still pending), **When** eligibility is read, **Then** the answer is completed without name and phone.
4. **Given** a logged-in skip, **When** retail-setup records it, **Then** `skip_until` equals the server's current instant plus 90 × 24 hours; a client-supplied timestamp is never used.
5. **Given** a row whose `skip_until` is in the future, **When** eligibility is read, **Then** the answer is skipped with that `skip_until`; **given** it is in the past, **Then** the answer is eligible.
6. **Given** a row with `completed_at`, **When** the same shopper skips, **Then** the row stays completed; completion has no expiry while the row exists.
7. **Given** the same email on two different projects, **When** eligibility is read on each, **Then** each project answers from its own row only.
8. **Given** a login where the browser has `complete` or `skip_until` and the server row is empty, **When** the promotion is requested, **Then** the row is created with that state; name and phone are stored only when the submitted phone matches a first-membership submit recorded by retail-setup for this project, and the stored values are the server-recorded ones.
9. **Given** a login where the server row already has `completed_at` or a future `skip_until`, **When** a promotion is requested, **Then** the server row is not weakened (completion is never replaced by a skip, a later `skip_until` is never shortened).
10. **Given** a write committed on one request, **When** the next eligibility read for the same project × email arrives, **Then** it sees that write (no cache, no replica lag).
11. **Given** no readable session email, **When** the widget would call eligibility, **Then** retail-setup has nothing to answer: anonymous shoppers have no row.

---

### User Story 4 - Abandoned-cart notifications carry and keep the Opt-in flag (Priority: P1)

The abandoned-cart script now sends `opt_in: true` (with the Opt-in name and phone) on `vtex:addToCart` and `orderFormUpdated` when it holds the confirmed pair. Agentic-cx forwards `opt_in` on the existing notification proxy. Retail-setup stores the flag on the cart, treats the register as idempotent per `order_form_id` and project, uses the Opt-in phone for flagged registers, and does not store the flag while Opt-in is off. Recovery still waits for the existing abandonment window and the existing dispatch.

**Why this priority**: Opt-in-attributed recovery (BD-020) and the later results screens depend on the flag being stored correctly and never lost.

**Independent Test**: With abandoned cart enabled and Opt-in on, send a flagged notification for an order form, then the unflagged page-load notification for the same order form with the VTEX profile phone. Verify one open cart for that order form, flagged, with the Opt-in phone. With Opt-in off, send a flagged notification and verify the cart is stored without the flag. Send a notification without the `opt_in` field and verify the behavior is identical to today's.

**Acceptance Scenarios**:

1. **Given** abandoned cart enabled and Opt-in on, **When** a notification arrives with `opt_in: true`, **Then** the cart for that order form and project is stored with the Opt-in flag and the notification's phone.
2. **Given** an open cart already registered for an order form and project, **When** a flagged notification arrives for the same order form, **Then** the existing record is updated with the flag and the Opt-in phone and no second cart is created for that order form.
3. **Given** an open flagged cart, **When** an unflagged notification (page load, 15-minute reschedule, or any notification without `opt_in`) arrives for the same order form, **Then** the flag and the Opt-in phone are kept.
4. **Given** Opt-in is off for the project, **When** a notification arrives with `opt_in: true`, **Then** the cart is processed as it is today and the flag is not stored.
5. **Given** the abandoned-cart automation is not enabled, **When** any notification arrives, **Then** the existing skip behavior applies unchanged and no flag is stored.
6. **Given** a notification without the `opt_in` field, **When** it is processed, **Then** the behavior is identical to the current contract.
7. **Given** a flagged cart that is later purchased, **When** the existing conversion handling runs, **Then** the cart keeps its flag so recovered Opt-in carts can be counted later.

---

### User Story 5 - Identifier is filled on a later login for contacts this feature created (Priority: P2)

An anonymous shopper who submits a new number gets a Flows contact with an empty identifier. When that shopper later logs in and the browser record is promoted, retail-setup fills the contact's identifier with the session email — but only for a contact this feature created, only when its identifier is still empty, and never for a contact that was only added to the group or was already in **Opt-in**.

**Why this priority**: It improves cross-channel identity (FR-010c in the product spec) but no shopper or merchant flow is blocked without it.

**Independent Test**: Submit a new number anonymously (contact created, identifier empty), then promote a browser `complete` with that phone for a logged-in email and verify the contact's identifier now equals the email. Repeat with a number that existed in Flows before the submit and verify the identifier is not touched.

**Acceptance Scenarios**:

1. **Given** a contact created by an anonymous Opt-in submit with an empty identifier, **When** a promotion for that phone and a session email reaches retail-setup, **Then** the contact's identifier is set to the normalized session email.
2. **Given** a contact whose identifier is not empty, **When** the same promotion arrives, **Then** the identifier is not overwritten.
3. **Given** a contact that was only added to **Opt-in**, or was already in **Opt-in**, **When** a promotion arrives, **Then** no field on that contact is changed.

---

### Edge Cases

- **Two submits for the same number on the same project at the same time** (two tabs, double click): at most one Flows contact is created and at most one coupon is sent; the second submit resolves as already-in-Opt-in.
- **Flows created the contact but the response was lost**: the retry lookup finds the contact already in **Opt-in** and follows the already-in-Opt-in outcome, so no coupon and no immediate enrollment happen for that submit. This is the behavior fixed by the architecture ("A retry that finds the contact already in Opt-in is outcome 4"); it is recorded here as a known limitation.
- **Retry attempts exhausted with no known outcome**: the submit stays recorded as unresolved and can be re-dispatched; it is not silently dropped (constitution IV). The logged-in row keeps `completed_at`.
- **Coupon turned off, sender disconnected, Shopping Assistant disabled, or Opt-in turned off while a submit is still pending**: when the outcome resolves, job 2 checks the coupon state at that moment and does not send; job 3 checks the abandoned-cart automation at that moment.
- **Abandoned-cart automation turned on after contacts were captured**: retail-setup never enrolls a sitting cart because of the toggle and never backfills; enrollment waits for the next flagged notification.
- **Submit carries an `orderFormId` whose order form cannot be read from VTEX**: the immediate enrollment is skipped and logged; the script will enroll the cart on the next qualifying cart event.
- **Coupon template not yet approved by Meta right after the coupon is turned on**: the coupon is not live, so no send is attempted (FR-028); first memberships in that window get no coupon, and completion is unaffected.
- **Coupon template or version removed in Integrations while the automation was inactive**: the next activation path finds it in the readiness check and repairs it before reactivating (FR-005a, FR-005b); the merchant sees no error.
- **Merchant edited the coupon message but Integrations still holds the old approved version**: the readiness check sees the misalignment and creates a new version from the edited local message; the old approved version is not used to overwrite the edit.
- **Shopper completes while the coupon template is pending (or rejected)**: success, no coupon, and no coupon after the approval either; the shopper saw the version without coupon.
- **Template approved between a no-coupon render and the submit**: job 2 checks approval at send time and may send; the shopper was not promised a coupon, so the send is a bonus, not a contradiction.
- **Template stops being approved between a coupon render and the submit**: job 2 does not send; the shopper still sees success (same as a coupon-send failure).
- **Template rejected by Meta and the merchant saves the coupon again without editing the message**: the repair does not recreate the rejected version (the same content would be rejected again); the coupon stays not live until the merchant edits the message in Automations and the new version is approved.
- **Template status cannot be read** (Integrations or the status source unavailable): treated as not approved — version without coupon, no send, warning in the merchant read; Opt-in capture is not blocked.
- **Merchant edits the coupon message in Automations while the coupon is live**: the new version goes back to review, the coupon stops being live until it is approved, and it then goes live again with no merchant action in Opt-in.
- **Sender changed to a number on another WhatsApp Business account**: the readiness check runs against the new sender's channel, so a template missing there is created before coupon-send is rebound.
- **Merchant edited the coupon message in Automations**: later sends use the edited message; turning the coupon off and on does not reset it to the default.
- **A user-created group named "Opt-in" already exists in the Flows org**: it is reused as the Opt-in group.
- **Ensuring the Opt-in group fails while turning Opt-in on**: the save is not reported as successful and Opt-in stays off, so settings never say "on" while the group is missing.
- **Session email with different case or surrounding spaces**: trimmed and lowercased before every read and write, so it resolves to the same row.
- **VTEX account renamed**: the eligibility row is keyed by project, so it survives the rename.
- **Submit request reaches retail-setup with a widget-supplied email field**: ignored; the email is taken only from the identity agentic-cx validated.
- **Promotion carries a phone that never reached first membership on this project**: the row is promoted without name and phone, so no `weni:opt-in-confirmed` restore and no flagged enrollment can be triggered with an unconfirmed number.
- **Submit outcome visible to the caller**: the response distinguishes first membership from already-in-Opt-in, as the architecture requires for the widget event. The shopper is never shown the difference (BD-014), but the outcome is observable on the network; this is accepted by the architecture and noted here.
- **Number valid in format but not on WhatsApp**: accepted (no existence check in v1); later sends may fail without undoing completion.
- **Sender changed while a submit is still pending**: the coupon goes out from the sender stored when job 2 runs, not the one stored when the submit was accepted.
- **Sender disconnected while other numbers stay connected**: the coupon turns off; the merchant must pick a sender and save the coupon on again. If no number remains, the coupon toggle can only be saved on again after a number is connected.
- **Two settings saves racing (sender change and coupon off)**: the last committed save wins, and coupon-send ends in the state that save describes (bound to the stored sender, active only if the coupon is on).
- **Connected numbers change between reading the admin screen and saving**: the save is validated against the numbers connected at save time; a sender that is no longer connected is rejected, and a project that went from one to two numbers now requires an explicit sender (unless the coupon is already on, in which case the stored sender is kept).
- **Disconnect event arrives late**: between the actual disconnect and the event, the coupon is still on and a first membership may trigger a send that fails at the channel; the failure is logged and does not undo completion.
- **Disconnect event duplicated, out of order, for an unknown project, or for a channel that is not the sender**: duplicates, events for a project whose coupon is already off, and events for a non-sender channel change nothing; events with no matching project are logged and ignored; nothing in the event, and no later channel creation, turns the coupon on.
- **Deletion event for a non-WhatsApp channel** (for example webchat): ignored.
- **Malformed deletion event** (missing project or channel identifier): logged and discarded; it does not block the queue or later events.
- **Sender number reconnected as a new channel**: Flows gives it a new channel identifier, so the old deletion never matches the new channel; the coupon stays off until the merchant saves it on again.
- **Shopping Assistant state written twice with the same value**: no side effect (coupon-send is not toggled again).
- **Traffic spike above the declared peak**: storefront reads keep answering and valid submits are accepted and resolved in the background; background work for Opt-in does not starve other retail-setup jobs.

## Requirements *(mandatory)*

### Functional Requirements

#### Merchant settings and enable gates

- **FR-001**: Retail-setup MUST store, per project, Opt-in on/off, coupon on/off, coupon discount percent, coupon code and coupon sender number. A project with no stored settings MUST read as Opt-in off and coupon off. Retail-setup MUST NOT turn Opt-in on for any project on its own (onboarding, migration, or feature release).
- **FR-002**: Retail-setup MUST reject turning Opt-in on unless Shopping Assistant is enabled for the project at save time, with a stable error code. The absence of an abandoned-cart automation or of a connected WhatsApp number MUST NOT block it.
- **FR-002a**: Retail-setup MUST be the source of truth for whether Shopping Assistant is enabled for each project. Agentic-cx writes that state whenever the merchant turns Shopping Assistant on or off. A project with no recorded state MUST be treated as Shopping Assistant not enabled. Writing the same state twice MUST have no further effect.
- **FR-003**: When Opt-in is turned on, retail-setup MUST make sure a Flows group named **Opt-in** exists in the project's org, reusing an existing group with that name. If the group cannot be ensured, the save MUST fail and Opt-in MUST stay off. Submits MUST NOT create the group.
- **FR-004**: Retail-setup MUST reject turning the coupon on unless at least one WhatsApp number is connected for the project at save time, with a stable error code. Retail-setup MUST accept a coupon code that does not resolve to a VTEX promotion and a percent that differs from the promotion's discount.
- **FR-004a**: A coupon-on save MUST be rejected with a field-level error, storing nothing and leaving coupon-send untouched, when the discount percent or the coupon code is missing, or when two or more WhatsApp numbers are connected and no sender is given. Retail-setup MUST NOT choose a sender on its own when two or more numbers are connected.
- **FR-004b**: With exactly one connected WhatsApp number at save time, retail-setup MUST store that number as the sender without requiring it in the request. With two or more, the given sender MUST be one of the project's connected numbers at save time; otherwise the save MUST be rejected with a field-level error.
- **FR-004c**: The merchant MAY change the sender while the coupon is on, to another connected number. The change MUST apply only to sends made after it; coupons already sent MUST NOT be sent again and contacts who completed before the change MUST NOT receive a send.
- **FR-004d**: Connecting another WhatsApp number MUST NOT change the stored sender or the coupon state, and MUST NOT force a new sender selection.
- **FR-005**: When the coupon is turned on, retail-setup MUST create the project's coupon-send automation seeded with the platform default template and bound to the sender number, or reactivate it if it already exists, keeping any message the merchant edited in Automations. A sender change MUST rebind the same automation. There MUST be at most one coupon-send automation per project.
- **FR-005a**: Every path that activates or reactivates coupon-send (coupon turned on, sender changed, Opt-in re-enabled, Shopping Assistant re-enabled) MUST first run a readiness check through Integrations, for the sender number's channel: the automation's template and its current version exist, and the template metadata stored in retail-setup is aligned with Integrations. The check MUST also read the current version's approval status, which decides whether the coupon is live (FR-005c) but is not itself a reason to repair. When the check passes, coupon-send is (re)activated.
- **FR-005b**: When the readiness check fails (template or current version missing, or metadata misaligned), retail-setup MUST repair it — recreating the template or version and realigning the metadata as needed — and then (re)activate coupon-send. The template metadata stored in retail-setup (including any merchant edit made in Automations) MUST be the source of truth: a misalignment MUST be repaired by creating a new version in Integrations from the local metadata, never by overwriting the local metadata with the Integrations copy. The readiness check and the repair MUST NOT turn into an error for the merchant: the coupon save succeeds. A current version that exists but is pending, rejected, paused or disabled MUST NOT be recreated by the repair; it only keeps the coupon not live until Meta approves it or the merchant edits the message in Automations.
- **FR-005c**: The coupon is **live** only when it is on, its sender number is connected, and the coupon-send template's current version is approved by Meta for that sender. Any other status — pending (including a version just recreated by the repair), rejected, paused, disabled, back in review after an edit in Automations, not approved for a newly selected sender, or unknown because the status cannot be read — MUST be treated as not live. Not live MUST NOT turn the coupon off, MUST NOT block a coupon save, and MUST NOT be reported as an error; the coupon stays on and saved. When the status becomes approved, the coupon MUST become live with no merchant action.
- **FR-005d**: Retail-setup MUST keep the approval status of the coupon-send template per sender up to date, so that a status change (to approved, or from approved to anything else) is reflected in the storefront read (FR-011), the merchant read (FR-010a) and job 2 (FR-028) within **15 minutes**, defined as a named setting.
- **FR-006**: Turning the coupon off, turning Opt-in off, or Shopping Assistant becoming disabled MUST deactivate the coupon-send automation without deleting it.
- **FR-007**: Opt-in settings changes MUST NOT create, activate, configure, or deactivate the abandoned-cart automation, and MUST NOT delete the **Opt-in** group or any contact.
- **FR-008**: When the recorded Shopping Assistant state changes to disabled, Opt-in MUST stay on and coupon settings MUST stay as saved; coupon-send MUST be deactivated. When Shopping Assistant is enabled again, coupon-send MUST be reactivated if Opt-in is on and the coupon is on (the coupon being on means its sender is still connected, per FR-009).
- **FR-009**: Retail-setup MUST consume the channel deletion event that Flows publishes on every channel deactivation (A9). When the deleted channel is the project's coupon sender, it MUST turn the coupon off and deactivate coupon-send, with no fallback to another connected number. The sender MUST be matched by the event's project and Flows channel identifier; the deletion of any other channel, including another WhatsApp number of the same project, MUST change nothing. Events for channel types other than WhatsApp MUST be ignored. Processing the same event more than once, or an event for a project whose coupon is already off, MUST have no further effect. An event that cannot be matched to a project, or whose payload is invalid, MUST be logged and ignored without blocking later events. No event, and no later channel creation, turns the coupon back on.
- **FR-009a**: The coupon sender MUST be stored with the Flows channel identifier of its WhatsApp channel (plus the phone number id, for diagnosis), so the deletion event can be matched to it without another lookup.
- **FR-010**: Re-enabling Opt-in MUST reactivate coupon-send when the coupon is on and Shopping Assistant is enabled.
- **FR-010a**: The merchant settings read MUST return the project's connected WhatsApp numbers and the current sender, so the admin screen can disable the toggle with no number, hide the selector with one, and show it without a pre-selection with two or more. While the coupon is on but not live because of the template status, it MUST also report that the template is awaiting approval, so the coupon section shows its warning; one indication covers every not-approved status (no distinct rejected state).
- **FR-011**: Retail-setup MUST expose a storefront-facing settings read that tells the widget whether the form is available (Opt-in on and Shopping Assistant enabled), whether the coupon is **live** (FR-005c), and the percent only while it is live. A coupon that is on but not live MUST be reported exactly like a coupon that is off, so the widget renders the version without coupon. It MUST NOT expose the coupon code, the sender number, or the template status. Because this read happens on every visit, it MAY be served from a short-lived shared cache, provided every settings or Shopping Assistant state change invalidates it immediately and template status changes are reflected within the FR-005d window.

#### Eligibility record

- **FR-012**: Retail-setup MUST keep at most one eligibility record per project × normalized session email, holding `completed_at`, `skip_until`, and — only after a first membership — the submitted name and WhatsApp phone. Normalization MUST be trim plus lowercase, applied before every read and write.
- **FR-013**: The eligibility read MUST answer eligible (no record, or `skip_until` in the past and no `completed_at`), completed (with name and phone when stored), or skipped with `skip_until`. It MUST NOT consider any phone known from VTEX profile, cart, or Flows.
- **FR-014**: Eligibility reads and writes MUST be served from the system of record so a committed write is visible to the next request; no shared cache may sit in front of them.
- **FR-015**: A logged-in skip MUST set `skip_until` to the server's current instant plus 90 × 24 hours. A skip MUST NOT replace an existing `completed_at`.
- **FR-016**: On a promotion request, retail-setup MUST create the record from the browser's `complete` or `skip_until` only when no record exists for that project × email; an existing record MUST NOT be weakened. Name and phone MUST be stored only when the phone matches a first-membership submit already recorded by retail-setup for that project, and the stored values MUST be the server-recorded ones.
- **FR-017**: Anonymous shoppers MUST NOT get an eligibility record.

#### Submit and job 1 (contact)

- **FR-018**: Retail-setup MUST re-validate every submit: non-empty name, a known country calling code, and a national number valid for that country. Invalid submits MUST be rejected with a field error, with no write and no Flows call. Retail-setup MUST NOT check whether the number exists on WhatsApp.
- **FR-019**: Retail-setup MUST normalize the number into the WhatsApp identity `whatsapp:<E.164 digits without a leading +>` and use it as the only lookup key in the project's Flows org. A `tel:` or webchat identity with the same digits MUST NOT count as a match.
- **FR-020**: For a logged-in submit, retail-setup MUST write `completed_at` on the eligibility record when it accepts the payload, before the Flows outcome is known.
- **FR-021**: Job 1 MUST resolve to exactly one outcome: (a) **new number** — create the WhatsApp contact with the submitted name, the identity and an identifier equal to the session email (empty when anonymous), in the **Opt-in** group; (b) **exists, not in Opt-in** — add that contact to the group without changing its identifier, name, or phone; (c) **already in Opt-in** — no Flows write. Outcomes (a) and (b) are first membership.
- **FR-022**: A Flows error payload that means "already in Opt-in" MUST map to outcome (c). A timeout, dropped connection, HTTP 5xx or HTTP 429 with no such payload MUST NOT map to outcome (c); it MUST be retried with a bounded number of attempts and a backoff, both named settings, until one of the three outcomes is known. Each attempt MUST start from a fresh lookup so a retry never creates a second contact.
- **FR-023**: When attempts are exhausted, the submit MUST remain recorded as unresolved, logged with context, and re-dispatchable.
- **FR-024**: Concurrent submits for the same project × WhatsApp identity MUST create at most one contact and trigger at most one coupon send and one immediate enrollment.
- **FR-025**: After a first membership by a logged-in shopper, retail-setup MUST store the submitted name and phone on the eligibility record. After outcome (c), it MUST NOT store them.
- **FR-026**: Retail-setup MUST record each submit's project, WhatsApp identity, outcome and whether the contact was created by this feature, so that retries, promotion checks (FR-016) and the identifier fill (FR-034) can be decided on the server.
- **FR-027**: The submit response MUST report first membership (with the confirmed name and phone) or already-in-Opt-in when the outcome is known within the request budget, and pending otherwise. A Flows failure MUST NOT turn into an error response for a submit that passed validation.

#### Job 2 (coupon)

- **FR-028**: After a first membership, retail-setup MUST send the coupon through the coupon-send automation only when, at that moment, the coupon is live (FR-005c) and coupon-send is active, and it MUST send from the sender number stored at that moment, never from another number. The sender being connected is represented by the coupon state, which the sender's disconnect event (FR-009) turns off; the template approval MUST be checked at send time. It MUST NOT wait for a cart. It MUST NOT send after outcome (c), and MUST NOT send to contacts who completed before the coupon was on.
- **FR-028a**: A first membership that happens while the coupon is not live MUST NOT receive the coupon, then or later: nothing is held or queued, and the coupon becoming live afterwards MUST NOT trigger a retroactive send. The skip MUST be logged with the project and submit identifiers.
- **FR-029**: A coupon-send failure MUST NOT undo completion and MUST NOT block job 3. Each first membership MUST produce at most one coupon send.

#### Job 3 and the abandoned-cart flag

- **FR-030**: After a first membership, when the abandoned-cart automation is enabled at that moment and the submit carried an `orderFormId` whose cart has at least one item, retail-setup MUST enroll that cart immediately with the submitted phone and the Opt-in flag, through the same processing as the abandoned-cart notification. Otherwise it MUST NOT enroll anything. It MUST NOT enroll after outcome (c).
- **FR-031**: The existing abandoned-cart notification MUST accept an optional `opt_in` boolean, defaulting to false, so current callers keep their contract. When `opt_in` is true, the abandoned-cart automation is enabled and Opt-in is on, retail-setup MUST store the flag on the cart and use the notification's phone for that cart. When Opt-in is off, the flag MUST NOT be stored.
- **FR-032**: Cart registration MUST be idempotent per `order_form_id` × project when a flagged register is involved: a flagged register for an order form with an open cart MUST update that cart instead of creating another, and an unflagged notification for an order form whose open cart is flagged MUST keep the flag and the Opt-in phone. One order form MUST NOT produce two recovery messages because of the flag.
- **FR-033**: Enrollment MUST only register the cart; the recovery message MUST still follow the existing abandonment window and dispatch. A flagged cart MUST keep its flag through the existing conversion handling.

#### Identifier fill

- **FR-034**: On a promotion for a session email, retail-setup MUST set the Flows contact's identifier to the normalized email only when the submit record shows the contact was created by this feature for that project and the contact's identifier is still empty. It MUST NOT change any field on contacts that were added to the group or already in **Opt-in**.

#### Trust, isolation, observability and contracts

- **FR-035**: Storefront endpoints MUST accept calls only with the retail token minted by agentic-cx after session validation. The project MUST be resolved from the VTEX account the token carries, and the shopper email MUST come only from the identity agentic-cx validated, never from a widget-supplied field.
- **FR-036**: Merchant settings endpoints MUST accept calls only from the agentic-cx backend proxy with the existing merchant authentication, scoped to the project the caller is authorized for.
- **FR-037**: Every record, read and write MUST be scoped to a single project; nothing written for one project may change what another project reads.
- **FR-038**: Logs and error reports MUST NOT contain shopper names, emails or phone numbers; they MUST carry opaque identifiers (project, VTEX account, submit identifier, outcome). Every reported error MUST carry the project and account identifiers.
- **FR-039**: Every call to Flows, VTEX and the automation provider MUST have an explicit timeout defined as a named setting.
- **FR-040**: New endpoints MUST be versioned. The change to the abandoned-cart notification MUST be backward compatible within its current version.
- **FR-041**: Background Opt-in work (Flows resolution and retries, coupon sends, immediate enrollments) MUST be isolated from other retail-setup background work, so a spike in Opt-in traffic cannot delay unrelated jobs, and MUST be able to scale out independently.

### Key Entities *(include if feature involves data)*

- **Opt-in settings**: Per project. Shopping Assistant enabled (written by agentic-cx; absent means not enabled), Opt-in on/off (default off), coupon on/off (default off), discount percent (shopper-facing copy), coupon code (used later to resolve the VTEX promotion for coupon-order counting), coupon sender number. Never exposes the code or the sender to the storefront.
- **Coupon sender number**: The connected WhatsApp number the coupon-send automation sends from. Implicit (stored by retail-setup) when the project has exactly one connected number; chosen by the merchant, with no pre-selection, when two or more are connected. Coupon-only: it does not affect abandoned cart, Bulk Send, or Opt-in capture. Its disconnect turns the coupon off.
- **Opt-in eligibility record**: One per project × normalized VTEX session email. `completed_at` (no expiry), `skip_until`, and the name and WhatsApp phone only after a first membership. No record means eligible. Anonymous shoppers have none.
- **Opt-in submit record**: One per accepted submit. Project, WhatsApp identity, resolution status (pending, resolved, exhausted), outcome (created, added, already in Opt-in), whether the contact was created by this feature, and the `orderFormId` when present. Drives retries, promotion checks and the identifier fill.
- **Coupon template approval status**: Meta status of the coupon-send template's current version for the coupon sender number. Only approved makes the coupon live; every other status, including unknown, is treated the same. Read-only from the Opt-in point of view.
- **Opt-in group** *(Flows)*: The project's group named **Opt-in**, ensured on enable. Its contact count is the future shopper-base metric.
- **Coupon-send automation**: The project's single Opt-in-specific automation in the existing Automations product, seeded with the platform default WhatsApp template, bound to the coupon sender number, activated and deactivated by the settings rules, never deleted by Opt-in.
- **Opt-in-attributed cart**: An existing abandoned-cart record with the Opt-in flag set, enrolled by a flagged notification or by the immediate enrollment at first membership.

## Success Criteria *(mandatory)*

### Inherited success criteria this slice contributes to

The product success criteria are inherited unchanged. Retail-setup's slice directly supports SC-001, SC-002, SC-004 (logged-in suppression), SC-012, SC-014, SC-015, SC-016, SC-017, SC-019 and SC-020. SC-018 (merchant completes coupon setup on the first attempt) depends on the admin screen; retail-setup supports it through clear field-level errors (FR-004a, FR-004b).

### Slice verification outcomes

- **SC-001**: 100% of projects without a merchant save read as Opt-in off; 0 projects can be saved as Opt-in on while Shopping Assistant is not enabled; 0 can be saved as coupon on while no WhatsApp number is connected, or with a missing discount, code, or (with two or more numbers) sender.
- **SC-002**: 0 abandoned-cart automations are created, activated, or deactivated by any Opt-in settings change.
- **SC-003**: 100% of already-in-Opt-in submits produce no Flows write, no coupon send and no cart enrollment.
- **SC-004**: 100% of exists-but-not-in-Opt-in submits add the contact to the group without changing its identifier, name, or phone.
- **SC-005**: 0 duplicate WhatsApp contacts are created by concurrent or retried submits for the same number on the same project.
- **SC-006**: 100% of accepted submits end either with a known outcome or as a recorded, re-dispatchable unresolved submit; none disappear.
- **SC-007**: A logged-in completion or skip suppresses the form on the next eligibility read from any browser for the same store, in 100% of cases.
- **SC-008**: 0 coupon sends happen for contacts who completed before the coupon was on, or after the sender's disconnect event was processed.
- **SC-009**: 100% of flagged carts keep the flag after later unflagged notifications for the same order form.
- **SC-010**: 0 log lines or error reports contain a shopper name, email or phone number.
- **SC-011**: At the declared peak (10,000 transactions per minute) and during spikes above it, 99% of storefront settings and eligibility reads are answered within 1 second, so the widget can meet the product's 3-second display target (NFR-001).
- **SC-012**: During a spike above the declared peak, 0 valid submits are rejected because of load; they are accepted and resolved in the background.
- **SC-013**: 100% of disconnect events for the coupon sender leave the coupon off and coupon-send inactive with no fallback to another number; 100% of disconnect events for a non-sender number leave the coupon unchanged; 0 reconnects turn the coupon back on.
- **SC-014**: 100% of coupon sends go out from the sender number stored at send time, and after a sender change 100% of later sends use the new number with 0 resends of coupons already sent.
- **SC-015**: 100% of coupon saves on projects with exactly one connected number succeed without a sender in the request and store that number as the sender; 0 coupon saves on projects with two or more numbers succeed without an explicit sender.
- **SC-016**: 0 coupon activations or reactivations return an error to the merchant because of a missing, unapproved, or misaligned template or version.
- **SC-017**: 0 coupon sends happen with a template that is not approved, and 0 retroactive sends happen to shoppers who completed while the coupon was not live. The storefront read reports the coupon as live within 15 minutes of an approval, and as not live within 15 minutes of losing it, in 100% of cases.
- **SC-018**: 100% of coupon saves while the template is not approved succeed, keep the coupon on, and make the merchant read report the awaiting-approval warning until the template is approved.

## Assumptions

- **A1 — Coupon-send automation**: The "existing Automations product" is the set of agents assigned to a project in retail-setup (the same surface as abandoned cart, order status and back-in-stock). Coupon-send is a new official agent assigned with a platform default WhatsApp template; "deactivate" means the assignment becomes inactive and is kept. The coupon template is a marketing template sent through the regular template broadcast path, not through Direct Send (which only carries utility templates).
- **A2 — WhatsApp connected**: A "connected number" is an active WhatsApp Cloud channel of the project; Flows owns the channel and Integrations mirrors it. A project may have several. The coupon save checks (FR-004, FR-004a, FR-004b) list them at save time; after that, the coupon state is kept consistent by the Flows deletion event for the sender's channel (FR-009, A9). Connecting a new number needs no event, because it never changes the coupon (FR-004d).
- **A2a — Discount percent**: Retail-setup accepts a discount percent greater than 0 and at most 100; the value is shopper-facing copy and is not checked against the VTEX promotion.
- **A3 — Flows operations**: The current Flows client can already look up a contact by URN (with its groups), create a contact in a group, add a contact to a group, and find or create a group by name; the back-in-stock subscriber flow already uses this pattern. Updating a contact's identifier (FR-034) is a new Flows operation. Delete/rename protection of the **Opt-in** group is a Flows responsibility (architecture, "Flows contact contract").
- **A4 — Request budget**: Submit runs one bounded Flows attempt inside the request; any retry happens in the background. Coupon send and immediate enrollment do not lengthen the response beyond that attempt.
- **A5 — Cart has items**: The immediate enrollment decides "at least one item" by reading the order form through the same processing the abandoned-cart notification already uses, which already marks empty carts.
- **A6 — Data retention**: The submit record keeps the WhatsApp identity and the creation flag for as long as identifier fill and promotion checks need them. The name is kept only on first-membership submits, because a later promotion stores the server-recorded name and phone (FR-016); it is cleared as soon as the outcome resolves as already in **Opt-in**. Exact retention is set in the plan.
- **A7 — Results**: The results screens (revenue, coupon orders, recovered carts, shopper base, campaign banner) are deferred by the architecture document; this spec only keeps the flag, the group and the coupon code they will read.
- **A8 — agentic-cx contract**: Agentic-cx forwards the validated session email with each storefront call and forwards `opt_in` on the existing abandoned-cart proxy; it applies its existing skip when the abandoned-cart automation is inactive. It writes the Shopping Assistant state to retail-setup on every merchant change and backfills the current state of existing projects before Opt-in is released; until a project is backfilled, Opt-in cannot be turned on for it.
- **A9 — Disconnect event (Flows `channel.deleted`)**: Flows is the source of truth for channels and publishes `channel.deleted` on every channel deactivation, to the topic exchange `flows-channel-events.topic` with routing key `channel.deleted.<channel_type>` (for example `channel.deleted.wac`). The body is a weni-eda envelope whose `data` carries `project_uuid`, `channel_uuid` (Flows channel uuid), `channel_type`, `address`, `is_active` and `occurred_at`; WhatsApp channels (`WAC`, `WA`) also carry `whatsapp` with the phone number, phone number id and WABA id. Retail-setup binds its own queue to that exchange, using the existing weni-eda consumer setup: `channel.deleted.wac` (WhatsApp Cloud only, matching A2) or `channel.deleted.*` filtered by `channel_type`; the binding is a plan decision. Integrations consumes the same event only to delete its own app and notifies no one else, so retail-setup must consume it directly. Nothing in the event turns a coupon back on.
- **A10 — Template approval status source**: Retail-setup already receives template status updates from Integrations through its existing template status webhook and keeps them on the template version; that is the primary source for the coupon-send approval status, with a read through Integrations (the same one the readiness check uses) to confirm or refresh it. Reading a template's current status from Integrations is a new client capability; today retail-setup only creates templates there.
