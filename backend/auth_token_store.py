# backend/auth_token_store.py

revoked_tokens: set[str] = set()


def revoke_token(token: str) -> None:
    """Mark a token as revoked."""
    from backend.production.config import enabled
    if enabled():
        from backend.production.security import revoke
        from backend.auth_security import decode_access_token
        return revoke(token,decode_access_token(token)["exp"])
    revoked_tokens.add(token)


def is_token_revoked(token: str) -> bool:
    """Check whether a token has been revoked."""
    from backend.production.config import enabled
    if enabled():
        from backend.production.security import revoked
        return revoked(token)
    return token in revoked_tokens
