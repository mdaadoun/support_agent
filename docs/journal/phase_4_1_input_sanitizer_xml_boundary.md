# Session 4.1: Input Sanitizer & XML Boundary Delimitation
**Date:** 2026-09-24

*Implemented hardened defensive input sanitization in `src/security/sanitizer.py`. The pipeline scrubs non-printable C0 and C1 control characters, strips zero-width and bidirectional override obfuscation (Trojan Source defense), neutralizes nested XML boundary tags and spoofed system/instruction delimiters via bounded iterative substitution, and encapsulates raw customer payloads within strict `<user_email>` XML boundaries.*

---

### 1. 🎓 Concepts Introduced
- **XML Boundary Delimitation:** A defensive prompt containment technique that wraps untrusted user input within well-defined XML tags (`<user_email>...</user_email>`) in all LLM system and agent prompts, establishing an explicit structural boundary between trusted system instructions and untrusted external data.
- **Control Character Scrubbing:** The systematic removal of non-printable ASCII control codes (C0/C1) and Unicode format characters (such as zero-width spaces and bidirectional overrides) from untrusted inputs to prevent visual deception, terminal escape injection, and regex evasion.
- **Nested Tag Spoofing:** An adversarial prompt injection vector where an attacker crafts nested, partial, or malformed XML tags (e.g., `</user_email>` or `<system>`) inside the user input to escape designated data boundaries and inject rogue operational instructions into the model context.
- **Trojan Source / Bidi Overrides:** Unicode control characters (such as U+202E Right-to-Left Override) that manipulate the visual rendering order of text without altering the logical byte sequence, used by attackers to disguise malicious payloads as benign phrases.
- **Fixed-Point Tag Sanitization:** The iterative application of tag removal rules until the payload reaches a steady state where no further prohibited delimiters exist, defeating recursive evasion techniques.
- **Passive Input Framing:** A core architectural constraint instructing the LLM that content inside specified XML tags must be treated strictly as passive semantic information rather than executable commands or operational authority.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Bounded Iterative Tag Neutralization vs. Single-Pass Regex Substitution
- **Option 1:** Single-pass `re.sub` substitution or complete HTML/XML entity escaping (`&lt;`, `&gt;`).
- **Option 2 (Selected):** Bounded iterative loop (up to 5 passes) replacing boundary tags and spoofed system markers with `[TAG_REMOVED]`.
- **Rationale:** Single-pass regex substitution is vulnerable to recursive reconstruction attacks (e.g., `<<user_email>/user_email>` or `</user_</user_email>email>`), where removing the inner tag creates a valid outer tag. A bounded loop guarantees convergence to a clean fixed point while preventing infinite execution loops. Full HTML escaping (`&lt;`, `&gt;`) would distort customer email text and degrade downstream NLP parsing.

#### Decision: Selective Control Character Scrubbing with Safe Whitespace Preservation
- **Option 1:** Strip all characters with `unicodedata.category(c) in ('Cc', 'Cf')` indiscriminately, or only strip ASCII NUL (`\x00`).
- **Option 2 (Selected):** Targeted scrubbing of C0 controls (`[\x00-\x08\x0b\x0c\x0e-\x1f]`), DEL and C1 controls (`[\x7f-\x9f]`), and Unicode bidi/format controls (`[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]`).
- **Rationale:** Indiscriminately stripping `Cc` category characters would delete standard formatting whitespace like line feeds (`\n`), carriage returns (`\r`), and horizontal tabs (`\t`), corrupting multi-line email legibility. Selective scrubbing targets non-printable codes and obfuscation controls to defeat visual spoofing without damaging structure.

#### Decision: Explicit [TAG_REMOVED] Token Substitution vs. Empty String Deletion
- **Option 1:** Replace matched tags with an empty string (`""`).
- **Option 2 (Selected):** Replace matched tags with `[TAG_REMOVED]`.
- **Rationale:** Replacing spoofed tags with an empty string can unintentionally concatenate adjacent words (e.g., `"refund</user_email>now"` becoming `"refundnow"`), impairing regex token extraction and downstream model comprehension. The explicit token `[TAG_REMOVED]` maintains token separation, provides unambiguous audit logs for security observability, and signals tampered payloads to evaluators.

#### Decision: Fail-Fast Domain Exception Shielding on Invalid Payload Types
- **Option 1:** Silently convert non-string inputs via `str(raw_text)` or allow raw `TypeError` / `AttributeError` to raise.
- **Option 2 (Selected):** Raise `BusinessRuleViolationError(error_code="INVALID_PAYLOAD_TYPE")`.
- **Rationale:** Coercing non-string types (such as `None` or `dict`) can mask upstream boundary deserialization bugs. Raising `BusinessRuleViolationError` conforms strictly to the Pax Universal Engineering Guardrails requiring explicit domain exception shielding and preventing naked Python runtime crashes.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/security/sanitizer.py
import re
from core.exceptions import BusinessRuleViolationError

TAG_REMOVAL_TOKEN: str = "[TAG_REMOVED]"

CONTROL_CHARS_PATTERN: re.Pattern[str] = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]"
)
USER_EMAIL_TAG_PATTERN: re.Pattern[str] = re.compile(
    r"<\s*/?\s*user_email(?:\s+[^>]*)?/?>",
    re.IGNORECASE,
)
SPOOFED_TAG_PATTERN: re.Pattern[str] = re.compile(
    r"<\s*/?\s*(?:system|system_prompt|instructions|developer|assistant|context|admin|rules)\b(?:\s+[^>]*)?/?>",
    re.IGNORECASE,
)

def scrub_control_characters(raw_text: str) -> str:
    if not isinstance(raw_text, str):
        raise BusinessRuleViolationError(
            f"Expected string payload, got {type(raw_text).__name__}",
            error_code="INVALID_PAYLOAD_TYPE",
        )
    return CONTROL_CHARS_PATTERN.sub("", raw_text)

def sanitize_tag_spoofing(text: str) -> str:
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
    cleaned = scrub_control_characters(raw_text)
    sanitized = sanitize_tag_spoofing(cleaned)
    return f"<user_email>\n{sanitized}\n</user_email>"
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **Control Character Scrubbing Implemented (`scrub_control_characters`)**: Strips non-printable ASCII/C1 codes and Unicode bidi/format overrides while preserving `\t`, `\n`, `\r`.
2. [x] **Fixed-Point Tag Sanitization Implemented (`sanitize_tag_spoofing`)**: Neutralizes opening/closing/self-closing `<user_email>` variants and spoofed system/instruction markers with `[TAG_REMOVED]`.
3. [x] **Defensive XML Encapsulation Implemented (`wrap_user_email_payload`)**: Packages sanitized email content within `<user_email>...</user_email>`.
4. [x] **Domain Exception Shielding (`BusinessRuleViolationError`)**: Rejects non-string payloads with normalized error code `INVALID_PAYLOAD_TYPE`.
5. [x] **Comprehensive Unit Test Suite (`tests/unit/test_sanitizer.py`)**: 137 tests passing including control code stripping, bidi evasion, recursive tag reconstruction, and invalid types.
6. [x] **Static Verification & CI Gates**: `make lint`, `make typecheck` (Mypy strict), and `make test` passing 100%.
