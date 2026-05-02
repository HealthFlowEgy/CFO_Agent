from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings
from app.db import get_db


class Session(BaseModel):
    user_id: str
    tenant_id: str
    role: str
    email: str
    name: str
    locale: str

    @property
    def pseudonymous_user_id(self) -> str:
        # Tenant-scoped pseudonym for Anthropic metadata.user_id (per SRS §6.10)
        return f"{self.tenant_id}:{self.user_id}"


def hash_password(plain: str) -> str:
    # bcrypt has a 72-byte input limit — truncate defensively (demo passwords are short).
    payload = plain.encode("utf-8")[:72]
    return bcrypt.hashpw(payload, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    payload = plain.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(payload, hashed.encode("utf-8"))
    except ValueError:
        return False


def issue_token(user_id: str, tenant_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}")


async def current_session(
    authorization: Optional[str] = Header(default=None),
    x_tenant_id: Optional[str] = Header(default=None),
) -> Session:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    user_id = payload["sub"]
    tenant_id = x_tenant_id or payload["tenant_id"]
    with get_db() as conn:
        row = conn.execute(
            """SELECT u.email, u.name, u.locale, tu.role
               FROM users u
               JOIN tenant_users tu ON tu.user_id = u.id
               WHERE u.id = %s AND tu.tenant_id = %s""",
            (user_id, tenant_id),
        ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "user has no access to tenant")
    return Session(
        user_id=user_id,
        tenant_id=tenant_id,
        role=row["role"],
        email=row["email"],
        name=row["name"],
        locale=row["locale"],
    )
