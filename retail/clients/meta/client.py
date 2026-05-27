from django.conf import settings

from typing import Any, Dict, List, Optional

from retail.interfaces.clients.meta.client import MetaClientInterface
from retail.clients.base import RequestClient


class MetaClient(MetaClientInterface, RequestClient):
    """
    HTTP client for the Meta Graph API endpoints used by Retail.

    Wraps the calls Retail makes to the WhatsApp Cloud / Flows API:
    template library lookup, encrypted Flow creation and publishing,
    and registration of the WhatsApp Business Encryption public key.
    """

    def __init__(self, token: Optional[str] = None, url: Optional[str] = None):
        self.token = token or settings.META_SYSTEM_USER_ACCESS_TOKEN
        self.url = url or settings.META_API_URL

    @property
    def _auth_headers(self) -> Dict[str, str]:
        """
        Bearer-only headers used by multipart uploads.

        Multipart endpoints must let ``requests`` set ``Content-Type``
        itself so the multipart boundary is included in the value.

        Returns:
            Dict with the ``Authorization`` header.
        """
        return {"Authorization": f"Bearer {self.token}"}

    @property
    def _json_headers(self) -> Dict[str, str]:
        """
        Bearer + JSON content type for the standard endpoints.

        Returns:
            Dict with ``Authorization`` and ``Content-Type`` headers.
        """
        return {**self._auth_headers, "Content-Type": "application/json"}

    def get_pre_approved_template(
        self, template_name: str, language: str
    ) -> Dict[str, Any]:
        """
        Searches Meta's pre-approved template library by name and language.

        Args:
            template_name: Name (or substring) to search for.
            language: BCP-47 language code accepted by Meta (e.g. "pt_BR").

        Returns:
            Dict with the raw library response (templates and pagination).
        """
        url = f"{self.url}/message_template_library/"

        params = {
            "search": template_name,
            "language": language,
        }

        response = self.make_request(
            url=url,
            method="GET",
            params=params,
            headers=self._json_headers,
        )

        return response.json()

    def fetch_library_template_by_name_and_language(
        self, template_name: str, language: str
    ) -> Optional[Dict[str, Any]]:
        """
        Returns the exact ``(name, language)`` match from Meta's library catalog.

        Meta's ``message_template_library`` endpoint takes ``search`` as a
        fuzzy match, so the response may include items whose name only
        partially matches and the cross-language variant when the
        requested locale is missing. The Direct Send path requires an
        EXACT match on both name and language; this method post-filters
        the fuzzy response from :meth:`get_pre_approved_template` per
        ``contracts/meta-library-catalog.md`` §3:

        - Returns the first item whose ``name == template_name``
          (case-sensitive) AND, when the item carries a ``language``
          field, whose ``language == language`` (case-sensitive).
        - Items without a ``language`` field fall through the language
          guard and are matched on name alone.
        - Returns ``None`` when no item satisfies both filters.
        """
        response = self.get_pre_approved_template(template_name, language)
        data = response.get("data") or []

        for item in data:
            if item.get("name") != template_name:
                continue
            item_language = item.get("language")
            if item_language is None or item_language == language:
                return item

        return None

    def create_flow(
        self,
        waba_id: str,
        name: str,
        categories: List[str],
        endpoint_uri: str,
        flow_json: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Creates an encrypted Flow on Meta tied to the given WABA.

        The created Flow starts in DRAFT and only becomes usable in
        messages after :meth:`publish_flow` is called for its id.

        Args:
            waba_id: WhatsApp Business Account id that will own the Flow.
            name: Flow name (visible in Meta's Flow Manager UI).
            categories: List of Meta Flow categories (e.g. ["SHOPPING"]).
            endpoint_uri: Webhook URL Meta calls to exchange data with
                the Flow. In the One-Click Payment use case this points
                at the payment microservice.
            flow_json: Full Meta Flow JSON definition (screens, layout,
                routing model).

        Returns:
            Dict with the created Flow payload (``id`` is the
            attribute used downstream to publish it).
        """
        url = f"{self.url}/{waba_id}/flows"
        payload = {
            "name": name,
            "categories": categories,
            "endpoint_uri": endpoint_uri,
            "flow_json": flow_json,
        }

        response = self.make_request(
            url=url,
            method="POST",
            json=payload,
            headers=self._json_headers,
        )

        return response.json()

    def register_public_key(
        self, phone_number_id: str, public_key_pem: str
    ) -> Dict[str, Any]:
        """
        Registers a WhatsApp Business Encryption public key for a phone.

        The endpoint hangs directly off the phone_number_id (no
        version segment) and expects a multipart/form-data body whose
        only field is ``business_public_key``.

        Args:
            phone_number_id: Meta Phone Number id that will use the key.
            public_key_pem: PEM-encoded RSA public key (SubjectPublicKeyInfo).

        Returns:
            Dict with Meta's response (typically ``{"success": true}``).
        """
        url = f"{settings.META_GRAPH_BASE_URL}/{phone_number_id}/whatsapp_business_encryption"

        response = self.make_request(
            url=url,
            method="POST",
            files={"business_public_key": (None, public_key_pem)},
            headers=self._auth_headers,
        )

        return response.json()

    def publish_flow(self, flow_id: str) -> Dict[str, Any]:
        """
        Publishes a previously created Meta Flow.

        Newly created flows start in DRAFT and can only be used in
        messages once explicitly published.

        Args:
            flow_id: Meta Flow id returned by :meth:`create_flow`.

        Returns:
            Dict with Meta's response (typically ``{"success": true}``).
        """
        url = f"{self.url}/{flow_id}/publish"

        response = self.make_request(
            url=url,
            method="POST",
            headers=self._json_headers,
        )

        return response.json()

    def submit_template_sample(
        self, waba_id: str, sample_body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Submit a ``message_samples`` payload for a WABA to classify.

        POSTs ``sample_body`` to ``{META_API_URL}/{waba_id}/message_samples``.

        Args:
            waba_id: WhatsApp Business Account id whose quota the sample
                charges against. Resolved per-call from
                ``ProjectOnboarding.config["channels"]["wpp-cloud"]["channel_data"]["waba_id"]``.
            sample_body: Wire-shape dict produced by
                ``retail.templates.adapters.direct_send_sample_translator.build_meta_sample_body``.

        Returns:
            Dict with Meta's response body verbatim. The happy-path
            shape is ``{"success": true, "category": "<UTILITY|MARKETING|AUTHENTICATION>"}``.
        """
        url = f"{self.url}/{waba_id}/message_samples"

        response = self.make_request(
            url=url,
            method="POST",
            json=sample_body,
            headers=self._json_headers,
        )

        return response.json()
