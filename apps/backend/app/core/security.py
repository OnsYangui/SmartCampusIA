"""Who is acting, as established by authentication (SA-28)."""

import uuid
from dataclasses import dataclass

# The five roles of the `user_role` PostgreSQL type (SA-13) and what they may do (SA-5 §3).
CANDIDATE = "candidate"
ACADEMIC_MANAGER = "academic_manager"
INTERVIEW_MANAGER = "interview_manager"
MANAGEMENT = "management"
ADMIN = "admin"

ROLES = frozenset({CANDIDATE, ACADEMIC_MANAGER, INTERVIEW_MANAGER, MANAGEMENT, ADMIN})
STAFF_ROLES = ROLES - {CANDIDATE}
# Staff roles bound to one institution (the `institution_scope` constraint of the users table).
INSTITUTION_ROLES = frozenset({ACADEMIC_MANAGER, INTERVIEW_MANAGER})
CATALOG_MANAGER_ROLES = frozenset({ACADEMIC_MANAGER, ADMIN})


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
        return self.role == ADMIN or self.institution_id == institution_id
