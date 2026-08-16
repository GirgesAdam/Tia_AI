from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.messages import HumanMessage

from app.agents.model_provider import active_model_label, build_chat_model
from app.agents.semantic_router import route_customer_message


def main() -> int:
    print(f"Main model: {active_model_label()}")

    route = route_customer_message(
        history=[
            HumanMessage(
                content="قولي سعر الليزر وعايز أحجز بكرة بعد الساعة 6"
            )
        ]
    )
    print("Semantic capabilities:", route.capabilities)
    print("Risk flags:", route.risk_flags)
    print("Flow signal:", route.flow_signal)

    response = build_chat_model().invoke("Reply with only: GEMINI_OK")
    text = response.text.strip()
    print("Main model response:", text)

    if text != "GEMINI_OK":
        raise RuntimeError("Gemini main-model smoke response was unexpected.")

    print("Gemini provider smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
