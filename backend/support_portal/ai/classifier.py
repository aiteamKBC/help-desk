from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DIRECT_REPLIES = {
    "closing": "Thank you for contacting Kent Help Desk. Get in touch again whenever you need support.",
    "human": "You can speak to a live agent using the Live Agent button on the right side of this chat, available between 08:00 and 16:00. You can also use Book Session if you would prefer to arrange a support time.",
    "booking": "Use the Book Session button on the right side of this chat to choose a support time between 08:00 and 16:00.",
}

CLOSING = {
    "thanks", "thank you", "thank u", "thx", "ty", "cheers", "much appreciated", "bye",
    "goodbye", "see you", "take care", "all good", "that's all", "nothing else",
    "ok thanks", "great thanks", "perfect thanks",
}
HUMAN = ("live agent", "human agent", "human", "speak to someone", "talk to someone", "speak with someone", "real person", "phone support", "phone", "call support", "call someone")
BOOKING = ("book session", "book a session", "booking", "support session", "schedule a session", "arrange a session")
GREETING = {"hi", "hii", "hiii", "hello", "hey", "heyy", "yo", "sup", "howdy", "good morning", "good afternoon", "good evening", "test", "testing", "ping", "check"}
FOLLOW_UP = ("still not working", "doesn't work", "does not work", "yes", "no", "okay", "where is it", "what do you mean", "more details", "continue")
INDICATORS = {
    "teams": ("teams", "microsoft teams", "microsoft", "ms365", "m365", "365", "outlook", "authenticator", "mfa"),
    "aptem": ("aptem", "otj", "off the job", "uln", "ilr", "plr", "portfolio", "e-portfolio", "learning plan", "timesheet"),
    "moodle": ("moodle", "lms", "learning management system", "e-learning", "gradebook", "quiz", "course"),
}


@dataclass(frozen=True)
class Classification:
    route: str
    direct_reply: str = ""


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _contains_any(text: str, values: tuple[str, ...] | set[str]) -> bool:
    return any(value in text for value in values)


def _explicit_platform(text: str) -> str:
    if "aptem" in text:
        return "aptem"
    if "microsoft teams" in text or "teams" in text:
        return "teams"
    if "moodle" in text or "lms" in text or "learning management system" in text:
        return "moodle"
    return ""


def _route_from_category(category: str, subcategory: str) -> str:
    text = f"{category} {subcategory}".lower()
    for route, indicators in INDICATORS.items():
        if _contains_any(text, indicators):
            return route
    return ""


def _score_route(text: str) -> str:
    scores = {
        route: sum(1 for indicator in indicators if indicator in text)
        for route, indicators in INDICATORS.items()
    }
    best_route, best_score = max(scores.items(), key=lambda item: item[1])
    return best_route if best_score > 0 else "general"


def classify(payload: dict[str, Any], previous_route: str = "") -> Classification:
    message = _clean(payload.get("message")).lower()
    ticket = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else {}
    category = _clean(ticket.get("category") or payload.get("category"))
    subcategory = _clean(
        ticket.get("subcategory")
        or ticket.get("technicalSubcategory")
        or payload.get("subcategory")
        or payload.get("technicalSubcategory")
    )
    issue_summary = _clean(ticket.get("summary") or ticket.get("inquiry") or payload.get("issueSummary") or payload.get("inquiry"))
    user_message_count = payload.get("messageCount")
    if not isinstance(user_message_count, int):
        messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
        user_message_count = sum(1 for item in messages if isinstance(item, dict) and item.get("sender") == "user")

    if message in CLOSING:
        return Classification("closing", DIRECT_REPLIES["closing"])
    if _contains_any(message, HUMAN):
        return Classification("human", DIRECT_REPLIES["human"])
    if _contains_any(message, BOOKING):
        return Classification("booking", DIRECT_REPLIES["booking"])
    if message in GREETING and user_message_count <= 1 and not issue_summary:
        learner = payload.get("learner") if isinstance(payload.get("learner"), dict) else {}
        first_name = _clean(learner.get("fullName")).split(" ", 1)[0]
        return Classification("greeting", f"Hi {first_name}, Charly here. What can I help you with?" if first_name else "Hi, Charly here. What can I help you with?")

    explicit_route = _explicit_platform(message)
    if explicit_route:
        return Classification(explicit_route)

    category_route = _route_from_category(category, subcategory)
    if category_route:
        return Classification(category_route)

    normalized_previous_route = _clean(previous_route).lower()
    if normalized_previous_route in {"teams", "aptem", "moodle", "general"} and _contains_any(message, FOLLOW_UP):
        return Classification(normalized_previous_route)

    return Classification(_score_route(f"{message} {issue_summary}".lower()))
