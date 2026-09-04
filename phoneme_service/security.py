"""Authentication adapter for the phoneme-assessment HTTP seam."""

import os
import secrets

from fastapi import Header, HTTPException, status

try:
    from phoneme_service.config import config
except ImportError:
    from config import config


def _bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


def require_authenticated_user(
    authorization: str | None = Header(default=None),
) -> str | None:
    if config.server.auth_mode == "off":
        return None

    token = _bearer_token(authorization)
    if config.server.auth_mode == "token":
        expected = os.environ.get(config.server.api_token_env, "")
        if not expected or not secrets.compare_digest(token, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return "service-token"

    if config.server.auth_mode == "firebase":
        try:
            import firebase_admin
            from firebase_admin import auth

            try:
                firebase_admin.get_app()
            except ValueError:
                firebase_admin.initialize_app()
            decoded = auth.verify_id_token(token, check_revoked=True)
            uid = str(decoded.get("uid", "")).strip()
            if not uid:
                raise ValueError("Firebase token has no uid")
            return uid
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired Firebase token.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication is not configured correctly.",
    )
