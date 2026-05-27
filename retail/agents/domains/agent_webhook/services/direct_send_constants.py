"""Direct Send Beta per-component character limits.

Enforced by ``Broadcast._exceeds_direct_send_length_limits`` at dispatch
and by ``_meta_library_template_fetch._validate_*`` at assignment.
Sourced from ``contracts/meta-library-catalog.md`` §5 and
``contracts/messaging-gateway-payload.md`` §3.1; see
``specs/002-direct-send-broadcasts/spec.md`` for the normative rules.
"""

MAX_BODY_LENGTH = 1024
MAX_HEADER_TEXT_LENGTH = 60
MAX_FOOTER_LENGTH = 60
MAX_BUTTON_LABEL_LENGTH = 20
