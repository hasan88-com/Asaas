"""
Asaas (اثاثہ) — Security

Supabase JWT verification and FastAPI auth dependency.
All auth is handled by Supabase; the backend only verifies tokens.
"""

from __future__ import annotations

import logging
import threading
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db

logger = logging.getLogger("asaas.security")

bearer_scheme = HTTPBearer()

# Asymmetric algorithms accepted from the Supabase JWKS endpoint. HS256 is
# handled separately with the shared secret, so it is intentionally excluded
# here to prevent algorithm-confusion attacks.
_ASYMMETRIC_ALGS = {"ES256", "RS256", "EdDSA"}

# In-memory JWKS cache: kid -> JWK dict. Populated lazily on first use and
# refreshed on a cache miss to tolerate Supabase key rotation.
_JWKS_CACHE: dict[str, dict] = {}
_JWKS_LOCK = threading.Lock()


def _jwt_key(raw: str) -> bytes:
    # GoTrue signs JWTs with []byte(secret) — raw UTF-8, not base64-decoded.
    return raw.encode("utf-8")


def _jwks_url() -> str:
    base = get_settings().supabase_url.rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json"


def _fetch_jwks() -> dict[str, dict]:
    """Fetch the Supabase JWKS and index it by kid."""
    url = _jwks_url()
    resp = httpx.get(url, timeout=10.0)
    resp.raise_for_status()
    keys = resp.json().get("keys", [])
    return {k["kid"]: k for k in keys if "kid" in k}


def _get_signing_key(kid: str) -> dict | None:
    """Return the JWK for ``kid``, fetching/refreshing the JWKS on a miss."""
    cached = _JWKS_CACHE.get(kid)
    if cached is not None:
        return cached
    with _JWKS_LOCK:
        if kid in _JWKS_CACHE:  # another thread populated it while we waited
            return _JWKS_CACHE[kid]
        try:
            fresh = _fetch_jwks()
        except Exception as exc:
            logger.warning("Failed to fetch Supabase JWKS from %s: %s", _jwks_url(), exc)
            return None
        _JWKS_CACHE.clear()
        _JWKS_CACHE.update(fresh)
        return _JWKS_CACHE.get(kid)


def verify_supabase_jwt(token: str) -> dict:
    """
    Verify a Supabase-issued JWT and return its payload.

    Supports both signing schemes: asymmetric keys (ES256/RS256/EdDSA) verified
    against the project's JWKS endpoint, and the legacy HS256 shared secret
    (SUPABASE_JWT_SECRET). Checks signature, expiry, and audience.
    """
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        logger.warning("JWT header unparseable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = header.get("alg", "")
    try:
        if alg in _ASYMMETRIC_ALGS:
            kid = header.get("kid")
            jwk_key = _get_signing_key(kid) if kid else None
            if jwk_key is None:
                raise JWTError(f"No JWKS signing key found for kid={kid!r} (alg={alg})")
            key: object = jwk_key
            algorithms = [alg]
        else:
            # Legacy HS256 shared-secret path.
            key = _jwt_key(settings.supabase_jwt_secret)
            algorithms = ["HS256"]
        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience="authenticated",
        )
        return payload
    except JWTError as exc:
        # Surface exactly why verification failed: the token's signing algorithm
        # and claims tell us whether this is an alg mismatch (asymmetric Supabase
        # signing keys), a wrong/empty secret, or an audience/expiry problem.
        try:
            header = jwt.get_unverified_header(token)
            claims = jwt.get_unverified_claims(token)
            logger.warning(
                "JWT verify failed: %s | alg=%s kid=%s aud=%r iss=%r exp=%s | "
                "secret_loaded=%s secret_len=%d",
                exc,
                header.get("alg"),
                header.get("kid"),
                claims.get("aud"),
                claims.get("iss"),
                claims.get("exp"),
                bool(settings.supabase_jwt_secret),
                len(settings.supabase_jwt_secret),
            )
        except Exception as decode_exc:  # malformed token, not even a JWT
            logger.warning("JWT verify failed and token is unparseable: %s", decode_exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    FastAPI dependency: verify Supabase JWT and return the local User record.
    Authorization on every protected endpoint (RULES.md C1.5).
    """
    from app.models.user import User

    payload = verify_supabase_jwt(credentials.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject claim.",
        )

    user_id = UUID(sub)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found. Call POST /auth/session to register your account.",
        )

    return user
