from typing import Protocol, Any


class _NoOpSupabaseClient(Protocol):
    """Minimal stub client to keep legacy imports working without Supabase."""

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - simple fallback
        raise RuntimeError("Supabase is no longer used in this project.")


_client: _NoOpSupabaseClient = object()  # type: ignore[assignment]


def get_supabase() -> _NoOpSupabaseClient:
    return _client
