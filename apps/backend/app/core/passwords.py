"""Password hashing with Argon2id (SA-28).

Hashes keep their own parameters, so `needs_rehash` lets the cost be raised later without
forcing a reset: a successful login re-hashes the password with the current parameters.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# Verified when the e-mail is unknown, so that "no such account" and "wrong password" take the
# same time and the response cannot be used to list the registered e-mails.
_DUMMY_HASH = _hasher.hash("smartcampus-timing-equalisation")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """False for a wrong password and for any value that is not a valid Argon2 hash.

    Demonstration accounts hold the placeholder "!disabled:…" until a demo password is configured:
    it is not an Argon2 hash, so nothing can ever match it.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def burn_time() -> None:
    verify_password("not-the-password", _DUMMY_HASH)
