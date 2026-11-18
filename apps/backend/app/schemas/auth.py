"""SA-28 — request and response bodies of the authentication routes."""

import uuid
from typing import Annotated

from pydantic import BaseModel, StringConstraints

# Plain constrained strings rather than EmailStr: the database holds the accounts, and a stricter
# syntax check would only turn a wrong e-mail into a 422 that tells attackers which are well formed.
Email = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=255)
]
# The upper bound keeps an oversized body from being fed to the (deliberately slow) Argon2 hasher.
Password = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class LoginIn(BaseModel):
    email: Email
    password: Password


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    institution_id: uuid.UUID | None
