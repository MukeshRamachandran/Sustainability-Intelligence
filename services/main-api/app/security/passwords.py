from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

_hasher = PasswordHasher(type=Type.ID)
_dummy_hash = _hasher.hash("not-a-real-user-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def consume_dummy_password_check(password: str) -> None:
    verify_password(_dummy_hash, password)


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_password_policy(password: str, minimum_length: int) -> None:
    if len(password) < minimum_length:
        raise ValueError("password does not meet minimum length policy")
    if password.isspace():
        raise ValueError("password cannot contain only whitespace")
