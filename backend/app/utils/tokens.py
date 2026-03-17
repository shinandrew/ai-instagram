import secrets


def generate_api_key() -> str:
    """Generate a 64-char hex API key."""
    return secrets.token_hex(32)


def generate_claim_token() -> str:
    """Generate a 64-char hex claim token."""
    return secrets.token_hex(32)


def generate_session_key() -> str:
    """Generate a 64-char hex session key."""
    return secrets.token_hex(32)
