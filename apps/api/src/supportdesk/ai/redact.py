"""Remove payment card numbers and credentials before any text reaches a model.

Customers paste card numbers and API keys into support chats. They stay in the
conversation (the agent may need them) but never leave for a model provider, local or
remote, and never land in the answer cache.
"""

from __future__ import annotations

import re

_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_SECRETS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),  # OpenAI style
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),  # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),  # GitHub tokens
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),  # Slack tokens
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),  # JWT
    re.compile(r"(?i)\b(password|passwd|pwd|passcode|otp|pin)\s*[:=]\s*\S+"),
]


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def redact(text: str) -> tuple[str, int]:
    """The text with secrets replaced, and how many were replaced."""
    count = 0

    def card(match: re.Match[str]) -> str:
        nonlocal count
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            count += 1
            return "[card number removed]"
        return match.group(0)

    text = _CARD.sub(card, text)
    for pattern in _SECRETS:
        text, n = pattern.subn(
            lambda m: (m.group(1) + ": [removed]") if m.lastindex else "[secret removed]", text
        )
        count += n
    return text, count
