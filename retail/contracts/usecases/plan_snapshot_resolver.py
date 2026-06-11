"""Resolve the chosen-plan snapshot captured at acceptance time.

The snapshot must freeze the plan the user chose at the exact moment of
acceptance, independent of future pricing changes. Today the chosen plan
lives on the ``Lead`` record (``plan`` + ``data``); this resolver is the
single seam to swap in a richer plan catalog (price, features, limits)
once a billing source exists.
"""

from typing import Optional

from retail.vtex.models import Lead


class PlanSnapshotResolver:
    def resolve(self, vtex_account: str, plan_id: Optional[str] = None) -> dict:
        lead = Lead.objects.filter(vtex_account=vtex_account).first()
        if lead is None:
            return {}

        return {
            "plan": lead.plan,
            "data": lead.data,
        }
