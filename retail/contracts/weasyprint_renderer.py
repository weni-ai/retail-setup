"""WeasyPrint-backed contract PDF renderer."""

from django.template.loader import render_to_string
from weasyprint import HTML

from retail.contracts.renderers import ContractPdfRendererInterface


class WeasyPrintContractPdfRenderer(ContractPdfRendererInterface):  # pragma: no cover
    """Render the contract HTML template to PDF bytes via WeasyPrint."""

    def render(self, template_name: str, context: dict) -> bytes:
        html = render_to_string(template_name, context)
        return HTML(string=html).write_pdf()
