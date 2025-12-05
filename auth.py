from typing import Optional

from fastapi import Depends


class UserContext:
    """Simple placeholder user context; real auth is handled externally (e.g. Bolt)."""

    def __init__(self, user_id: str = "anonymous", email: str = "", tenant_id: str = "", role: str = "member"):
        self.user_id = user_id
        self.email = email
        self.tenant_id = tenant_id
        self.role = role


async def get_current_user(_: Optional[str] = Depends(lambda: None)) -> UserContext:
    """Return a default unauthenticated user context.

    This keeps the dependency signature for routes that might import it,
    without relying on Supabase or any external auth provider.
    """

    return UserContext()
