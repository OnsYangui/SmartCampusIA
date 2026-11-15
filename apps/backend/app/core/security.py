"""Who is acting, as established by authentication (SA-28)."""

import uuid
from dataclasses import dataclass

CATALOG_MANAGER_ROLES = frozenset({"academic_manager", "admin"})


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    role: str
    institution_id: uuid.UUID | None

    @property
    def manages_catalog(self) -> bool:
        return self.role in CATALOG_MANAGER_ROLES

    def can_manage(self, institution_id: uuid.UUID) -> bool:
        """RM-09: an academic manager only acts on their own institution."""
        return self.role == "admin" or self.institution_id == institution_id
