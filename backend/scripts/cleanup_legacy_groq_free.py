from __future__ import annotations

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

LEGACY_PATHS = (
    BACKEND_DIR / "app/agents/llm_resilience.py",
    BACKEND_DIR / "app/agents/free_tier_fast_path.py",
    BACKEND_DIR / "tests/test_llm_resilience_helpers.py",
    BACKEND_DIR / "tests/test_agent_free_tier_budget.py",
    BACKEND_DIR / "tests/test_free_tier_booking_fast_path.py",
    BACKEND_DIR / "tests/test_groq_semantic_model_budget.py",
    BACKEND_DIR / "tests/test_structured_output_400_surface.py",
    BACKEND_DIR / "tests/test_structured_output_strategy.py",
    BACKEND_DIR / "tests/test_router_not_tool_call_structured_output.py",
    BACKEND_DIR / "scripts/run_agent_free_tier_regression.py",
    BACKEND_DIR / "AGENT_FREE_TIER.md",
    BACKEND_DIR / "AGENT_FREE_TIER_BOOKING.md",
    BACKEND_DIR / "GROQ_FREE_SEMANTIC_BUDGET.md",
    BACKEND_DIR / "STRUCTURED_OUTPUT_PROVIDER_NOTES.md",
)


def main() -> int:
    removed = 0
    for path in LEGACY_PATHS:
        if path.exists() and path.is_file():
            path.unlink()
            removed += 1
            print(f"[REMOVED] {path.relative_to(PROJECT_DIR)}")

    print(f"Legacy Groq/Free-tier cleanup complete. Removed={removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
