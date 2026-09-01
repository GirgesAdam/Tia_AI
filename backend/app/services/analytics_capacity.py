from __future__ import annotations


def is_statement_timeout(exc: BaseException) -> bool:
    """Detect PostgreSQL query-canceled errors caused by statement_timeout."""
    original = getattr(exc, "orig", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if sqlstate == "57014":
        return True
    message = str(original or exc).lower()
    return "statement timeout" in message or "canceling statement due to statement timeout" in message
