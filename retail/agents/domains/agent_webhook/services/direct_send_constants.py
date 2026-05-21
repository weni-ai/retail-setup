"""Direct Send Beta per-component length limits.

Single source of truth for the per-component character limits Meta
enforces on Direct Send Beta v1 messages. Imported by:

- ``direct_send_payload_builder`` / ``Broadcast.build_direct_send_message``
  (dispatch-time post-substitution check — T013), and
- ``adapt_meta_library_template_response`` in
  ``retail/templates/usecases/_meta_library_template_fetch.py``
  (assignment-time pre-substitution check — T023).

References:

- ``contracts/meta-library-catalog.md`` §5 (Direct Send Beta supported
  component set and per-component limits).
- ``contracts/messaging-gateway-payload.md`` §3.1 (length limits per
  message component on the Direct Send wire shape).

``MAX_BUTTON_LABEL_LENGTH`` is named generically because it bounds
BOTH ``cta_url.display_text`` (the visible button label, NOT the URL
itself — URLs can be much longer, see
``contracts/messaging-gateway-payload.md`` §3.3) AND ``reply.title``.
If Meta ever updates either limit independently, split into
``MAX_CTA_DISPLAY_TEXT_LENGTH`` + ``MAX_REPLY_TITLE_LENGTH`` (same
value at v1).
"""

MAX_BODY_LENGTH = 1024
MAX_HEADER_TEXT_LENGTH = 60
MAX_FOOTER_LENGTH = 60
MAX_BUTTON_LABEL_LENGTH = 20
