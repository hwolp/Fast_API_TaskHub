import hashlib
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from jwt.algorithms import RSAAlgorithm
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core import messages
from app.core.config import settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.models.enums import TokenType

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("taskhub-dummy-password")
ROOT = Path(__file__).resolve().parents[2]


def unauthorized(detail: str) -> UnauthorizedError:
    return UnauthorizedError(detail)


def forbidden(detail: str = messages.FORBIDDEN) -> ForbiddenError:
    return ForbiddenError(detail)


@lru_cache(maxsize=8)
def read_key(path: str) -> bytes:
    return (ROOT / path).read_bytes()


def load_keys() -> None:
    for key_path in (settings.JWT_PRIVATE_KEY_PATH, settings.JWT_PUBLIC_KEY_PATH):
        if (ROOT / key_path).exists():
            read_key(key_path)


def get_public_jwk() -> dict[str, list[dict[str, Any]]]:
    key = load_pem_public_key(read_key(settings.JWT_PUBLIC_KEY_PATH))
    public_jwk = json.loads(RSAAlgorithm.to_jwk(key))
    public_jwk.update(kid=settings.JWT_KEY_ID, use="sig", alg="RS256")
    return {"keys": [public_jwk]}


def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hash.verify(password, hashed)
    except (UnknownHashError, ValueError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(
    user_id: int, role: str, token_type: TokenType
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    duration = (
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        if token_type == TokenType.ACCESS
        else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    expires = now + duration
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": token_type.value,
        "jti": str(uuid4()),
        "iat": now,
        "exp": expires,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }
    return (
        jwt.encode(
            payload,
            read_key(settings.JWT_PRIVATE_KEY_PATH),
            algorithm="RS256",
            headers={"kid": settings.JWT_KEY_ID},
        ),
        expires,
    )


def decode_token(token: str, token_type: TokenType) -> dict:
    try:
        payload = jwt.decode(
            token,
            read_key(settings.JWT_PUBLIC_KEY_PATH),
            algorithms=["RS256"],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            leeway=30,
            options={
                "require": [
                    "sub",
                    "role",
                    "type",
                    "jti",
                    "iat",
                    "exp",
                    "iss",
                    "aud",
                ]
            },
        )
        if payload["type"] != token_type.value or not payload["sub"].isdigit():
            raise jwt.InvalidTokenError()
        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError(messages.TOKEN_EXPIRED) from None
    except jwt.InvalidTokenError:
        raise UnauthorizedError(messages.TOKEN_INVALID) from None
