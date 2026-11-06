import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt
from fastapi import HTTPException
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import settings

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("taskhub-dummy-password")
ROOT = Path(__file__).resolve().parents[2]


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def read_key(path: str) -> bytes:
    return (ROOT / path).read_bytes()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hash.verify(password, hashed)
    except (UnknownHashError, ValueError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(user_id: int, role: str, token_type: str) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    duration = (
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        if token_type == "access" else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    expires = now + duration
    payload = {
        "sub": str(user_id), "role": role, "type": token_type,
        "jti": str(uuid4()), "iat": now, "exp": expires,
        "iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE,
    }
    return jwt.encode(
        payload, read_key(settings.JWT_PRIVATE_KEY_PATH), algorithm="RS256",
        headers={"kid": settings.JWT_KEY_ID},
    ), expires.replace(tzinfo=None)


def decode_token(token: str, token_type: str) -> dict:
    try:
        payload = jwt.decode(
            token, read_key(settings.JWT_PUBLIC_KEY_PATH), algorithms=["RS256"],
            issuer=settings.JWT_ISSUER, audience=settings.JWT_AUDIENCE, leeway=30,
            options={"require": ["sub", "role", "type", "jti", "iat", "exp", "iss", "aud"]},
        )
        if payload["type"] != token_type or not payload["sub"].isdigit():
            raise jwt.InvalidTokenError()
        return payload
    except jwt.ExpiredSignatureError:
        raise unauthorized("token_expired") from None
    except jwt.InvalidTokenError:
        raise unauthorized("token_invalid") from None
