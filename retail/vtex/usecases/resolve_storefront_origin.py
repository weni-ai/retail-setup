from dataclasses import dataclass
from urllib.parse import urlparse

from retail.projects.models import Project


@dataclass(frozen=True)
class StorefrontOrigin:
    origin: str
    used_default: bool


def resolve_storefront_origin(project: Project) -> StorefrontOrigin:
    """Shopper-facing store origin: ``https://{host}`` with no path.

    Prefers ``project.config["vtex_host_store"]``. Falls back to
    ``{vtex_account}.myvtex.com`` — never ``vtexcommercestable``.
    """
    vtex_host_store = (project.config or {}).get("vtex_host_store")
    if vtex_host_store:
        host = urlparse(vtex_host_store).netloc
        if host:
            return StorefrontOrigin(origin=f"https://{host}", used_default=False)
    return StorefrontOrigin(
        origin=f"https://{project.vtex_account}.myvtex.com",
        used_default=True,
    )
