"""Defensive prompt isolation, XML framing, and entity extraction."""

import re

ORDER_ID_PATTERN = re.compile(r"CMD-[0-9]{5,8}")
EMAIL_PATTERN = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")

INJECTION_PATTERNS = (
    r"ignore\s+previous\s+instructions",
    r"system\s+override",
    r"you\s+are\s+now",
    r"dan\s+mode",
    r"bypass\s+rules",
    r"grant\s+refund",
    r"approve\s+compensation",
)


def wrap_user_email_payload(raw_text: str) -> str:
    """Sanitize raw inbound email text and enclose inside XML boundaries."""
    # Prevent XML breakout attacks
    sanitized = re.sub(
        r"</\s*user_email\s*>",
        "[TAG_REMOVED]",
        raw_text,
        flags=re.IGNORECASE,
    )
    return f"<user_email>\n{sanitized}\n</user_email>"


def extract_order_id(raw_text: str) -> str | None:
    """Extract standard order identifier from text using deterministic regex."""
    match = ORDER_ID_PATTERN.search(raw_text)
    return match.group(0) if match else None


def extract_email(raw_text: str) -> str | None:
    """Extract email address from text using regex."""
    match = EMAIL_PATTERN.search(raw_text)
    return match.group(0) if match else None


def detect_prompt_injection(raw_text: str) -> list[str]:
    """Scan raw text for known prompt injection and override signatures."""
    detected: list[str] = []
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, raw_text, flags=re.IGNORECASE):
            detected.append(pattern)
    return detected
