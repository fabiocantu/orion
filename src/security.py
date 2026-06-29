from __future__ import annotations

import base64
import hashlib
import hmac
import os


HASH_PREFIX = "pbkdf2_sha256"
ITERATIONS = 260_000
SALT_BYTES = 16


def hash_password(password: str) -> str:
    password_bytes = password.strip().encode("utf-8")
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, ITERATIONS)
    return "$".join(
        [
            HASH_PREFIX,
            str(ITERATIONS),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def is_password_hash(value: object) -> bool:
    return str(value or "").startswith(f"{HASH_PREFIX}$")


def verify_password(password: str, stored_password: str) -> bool:
    if not is_password_hash(stored_password):
        return hmac.compare_digest(password, stored_password or "")

    try:
        _, iterations_text, salt_text, digest_text = stored_password.split("$", 3)
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text.encode("ascii"))
        expected = base64.b64decode(digest_text.encode("ascii"))
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.strip().encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)
