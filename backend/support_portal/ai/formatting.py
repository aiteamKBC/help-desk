from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

CONTROLLED_FAILURE_REPLY = "I couldn't complete that response just now. Please try again. If the problem continues, use the Live Agent or Book Session button on the right side of this chat."


def response_payload(*, success: bool, route: str, reply: str, processing_ms: int) -> dict[str, Any]:
    status = "success" if success else "error"
    return {
        "success": success,
        "route": route,
        "reply": reply,
        "message": reply,
        "text": reply,
        "response": reply,
        "output": reply,
        "status": status,
        "processingMs": processing_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
