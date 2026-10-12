# backend/auth_token_store.py

revoked_tokens: set[str] = set()


def revoke_token(token: str) -> None:
    """Mark a token as revoked."""
    revoked_tokens.add(token)


def is_token_revoked(token: str) -> bool:
    """Check whether a token has been revoked."""
    return token in revoked_tokens