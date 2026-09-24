"""Defensive prompt isolation, XML framing, and entity extraction."""

import re

from core.exceptions import BusinessRuleViolationError

__all__ = [
    "CONTROL_CHARS_PATTERN",
    "EMAIL_PATTERN",
    "INJECTION_PATTERNS",
    "ORDER_ID_PATTERN",
    "SPOOFED_TAG_PATTERN",
    "TAG_REMOVAL_TOKEN",
    "USER_EMAIL_TAG_PATTERN",
    "detect_prompt_injection",
    "extract_email",
    "extract_order_id",
    "sanitize_tag_spoofing",
    "scrub_control_characters",
    "wrap_user_email_payload",
]

TAG_REMOVAL_TOKEN: str = "[TAG_REMOVED]"

ORDER_ID_PATTERN: re.Pattern[str] = re.compile(r"CMD-[0-9]{5,8}")
EMAIL_PATTERN: re.Pattern[str] = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")

# ASCII control chars (excluding \t \n \r), DEL, C1 controls, and Unicode bidi/format controls
CONTROL_CHARS_PATTERN: re.Pattern[str] = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]"
)

# Opening, closing, or self-closing user_email boundary tags
USER_EMAIL_TAG_PATTERN: re.Pattern[str] = re.compile(
    r"<\s*/?\s*user_email(?:\s+[^>]*)?/?>",
    re.IGNORECASE,
)

# Spoofed prompt/role/system XML delimiters attempting instruction override
SPOOFED_TAG_PATTERN: re.Pattern[str] = re.compile(
    r"<\s*/?\s*(?:system|system_prompt|instructions|developer|assistant|context|admin|rules)\b(?:\s+[^>]*)?/?>",
    re.IGNORECASE,
)

INJECTION_PATTERNS: tuple[str, ...] = (
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"system\s+override",
    r"developer\s+override",
    r"admin\s+override",
    r"you\s+are\s+now",
    r"pretend\s+you\s+are",
    r"dan\s+mode",
    r"developer\s+mode",
    r"jailbreak",
    r"bypass\s+rules",
    r"bypass\s+limits",
    r"grant\s+refund",
    r"approve\s+compensation",
    r"reveal\s+system\s+prompt",
    r"disregard\s+prior\s+rules",
)


def scrub_control_characters(raw_text: str) -> str:
    """Scrub non-printable control characters, C1 codes, and bidi/format overrides.

    Preserves valid whitespace characters: line feeds (\\n), carriage returns (\\r),
    and horizontal tabs (\\t).
    """
    if not isinstance(raw_text, str):
        raise BusinessRuleViolationError(
            f"Expected string payload, got {type(raw_text).__name__}",
            error_code="INVALID_PAYLOAD_TYPE",
        )
    return CONTROL_CHARS_PATTERN.sub("", raw_text)


def sanitize_tag_spoofing(text: str) -> str:
    """Neutralize nested boundary tags and spoofed system/instruction delimiters.

    Runs iteratively to ensure recursively constructed nested tags
    (e.g., <<user_email>/user_email>) cannot evade sanitization.
    """
    if not isinstance(text, str):
        raise BusinessRuleViolationError(
            f"Expected string payload, got {type(text).__name__}",
            error_code="INVALID_PAYLOAD_TYPE",
        )
    sanitized = text
    for _ in range(5):
        updated = USER_EMAIL_TAG_PATTERN.sub(TAG_REMOVAL_TOKEN, sanitized)
        updated = SPOOFED_TAG_PATTERN.sub(TAG_REMOVAL_TOKEN, updated)
        if updated == sanitized:
            break
        sanitized = updated
    return sanitized


def wrap_user_email_payload(raw_text: str) -> str:
    """Sanitize raw inbound email text and enclose inside XML boundaries.

    Scrubs non-printable control characters and neutralizes nested tag spoofing
    attempts before wrapping within <user_email> delimiters.
    """
    cleaned = scrub_control_characters(raw_text)
    sanitized = sanitize_tag_spoofing(cleaned)
    return f"<user_email>\n{sanitized}\n</user_email>"


def extract_order_id(raw_text: str) -> str | None:
    """Extract standard order identifier from text using deterministic regex."""
    if not isinstance(raw_text, str):
        raise BusinessRuleViolationError(
            f"Expected string payload, got {type(raw_text).__name__}",
            error_code="INVALID_PAYLOAD_TYPE",
        )
    match = ORDER_ID_PATTERN.search(raw_text)
    return match.group(0) if match else None


def extract_email(raw_text: str) -> str | None:
    """Extract email address from text using regex."""
    if not isinstance(raw_text, str):
        raise BusinessRuleViolationError(
            f"Expected string payload, got {type(raw_text).__name__}",
            error_code="INVALID_PAYLOAD_TYPE",
        )
    match = EMAIL_PATTERN.search(raw_text)
    return match.group(0) if match else None


def detect_prompt_injection(raw_text: str) -> list[str]:
    """Scan raw text for known prompt injection and override signatures."""
    if not isinstance(raw_text, str):
        raise BusinessRuleViolationError(
            f"Expected string payload, got {type(raw_text).__name__}",
            error_code="INVALID_PAYLOAD_TYPE",
        )
    detected: list[str] = []
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, raw_text, flags=re.IGNORECASE):
            detected.append(pattern)
    return detected
