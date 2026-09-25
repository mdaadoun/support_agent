# Session 4.4: Pre-Extraction Intent Classifier & Threat Guard
**Date:** 2026-09-25

*Implemented the Pre-Extraction Intent Classifier in `src/security/pre_extraction.py` and exported through `src/security/__init__.py`. The engine provides deterministic pre-flight evaluation of inbound customer inquiries before entering tool execution or ReAct reasoning loops. It detects aggressive legal litigation threats and profanity (`TC-11`), short-circuits order-dependent inquiries lacking a valid order identifier into `INFORMATION_MISSING` (`TC-05`) with zero tool calls, identifies out-of-scope non-ecommerce inquiries (`OUT_OF_SCOPE`), and decomposes multi-intent inquiries (`MIXED_QUERY`) into isolated sub-queries (`sub_queries`).*

---

### 1. 🎓 Concepts Introduced
- **Pre-Flight Intent Classification:** Deterministic parsing and categorization of inbound customer communications before entering costly LLM reasoning loops or invoking external tool APIs.
- **Missing Information Short-Circuiting (TC-05):** The immediate classification of an order-dependent inquiry as `INFORMATION_MISSING` when no valid order ID (`CMD-[0-9]{5,8}`) is present, preventing wasteful ERP lookups and initiating a clarification response.
- **Hostile Legal Threat Escort (TC-11):** Automated identification of litigation notices, attorney representation, small claims actions, and aggressive hostility (`is_legal_threat_or_aggressive=True`) resulting in `OUT_OF_SCOPE` classification and direct escalation to human legal staff with zero tool calls.
- **Intent Family Grouping:** Categorization of intents into functional domains (logistics tracking, financial refunds, documentation) to discern whether an inquiry contains distinct multi-intent actions (`MIXED_QUERY`).
- **Sub-Query Decomposition:** Parsing and splitting of compound customer inquiries into distinct, actionable sub-query clauses stored as an immutable tuple within `ExtractedDemand`.
- **Zero-Tool Pre-Extraction Gate:** Architectural boundary filter ensuring that invalid, incomplete, hostile, or irrelevant inquiries halt before dispatching tools, saving latency, compute tokens, and backend load.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Short-Circuiting Incomplete Requests to INFORMATION_MISSING (TC-05)
- **Option 1:** Allow the LLM loop to invoke tools and discover `order_id` is missing during runtime.
- **Option 2 (Selected):** Short-circuit during pre-extraction: If intent depends on an order but `order_id` is None, set intent to `INFORMATION_MISSING`.
- **Rationale:** Order lookup tools (`get_order_details`, `calculate_refund_eligibility`, `calculate_delivery_delay`) strictly require a validated order ID and customer email. Allowing inquiries lacking order identifiers into the ReAct loop consumes unnecessary LLM inference tokens and risks hallucinated tool arguments. Short-circuiting directly satisfies TC-05, returning an immediate clarification request with zero tool executions.

#### Decision: Immediate Out-of-Scope Escort for Legal & Hostile Threats (TC-11)
- **Option 1:** Treat legal threats as normal inquiries and attempt automated resolution.
- **Option 2 (Selected):** Classify queries with legal litigation threats or aggressive hostility as `OUT_OF_SCOPE` with `is_legal_threat_or_aggressive=True`.
- **Rationale:** Autonomous LLMs must never negotiate or commit company liability in legal disputes, litigation notices, or abusive scenarios. Flagging hostility and categorizing as `OUT_OF_SCOPE` guarantees 0 tool calls and triggers deterministic routing to human legal teams per corporate compliance policies.

#### Decision: Functional Intent Family Grouping for MIXED_QUERY Detection
- **Option 1:** Treat any query matching more than one regex keyword as `MIXED_QUERY`.
- **Option 2 (Selected):** Group related intents into functional families (Logistics: `ORDER_STATUS` + `DELIVERY_DELAY`; Refund: `REFUND_REQUEST`; Info: `ORDER_INFORMATION`) and only trigger `MIXED_QUERY` across distinct families or multiple order IDs.
- **Rationale:** Natural language queries frequently combine overlapping logistics terms (e.g. "Where is my order? It is delayed"). Treating these as `MIXED_QUERY` causes excessive decomposition and fragmented handling. Functional family clustering correctly treats related logistics terms as single-intent inquiries while cleanly identifying genuine multi-domain requests.

#### Decision: Dual Ingestion Interface (Structured Message vs. Raw Text)
- **Option 1:** Only accept `InboundEmailMessage` models.
- **Option 2 (Selected):** Provide both `InboundEmailMessage` ingestion (`classify`) and raw text/email evaluation (`classify_text`).
- **Rationale:** The API ingress and event streams pass validated `InboundEmailMessage` instances, whereas internal testing tools, CLI runners, and unit tests frequently operate on raw text and email strings. Providing dual entrypoints while sharing core evaluation logic simplifies testing and respects layer isolation.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/security/pre_extraction.py
from core.exceptions import BusinessRuleViolationError
from models.email import InboundEmailMessage
from models.enums import IntentEnum
from models.extraction import ExtractedDemand
from security.access_control import AccessControlGuard
from security.sanitizer import extract_all_order_ids, extract_order_id, scrub_control_characters

class PreExtractionClassifier:
    @classmethod
    def classify(cls, inbound: InboundEmailMessage) -> ExtractedDemand:
        if not isinstance(inbound, InboundEmailMessage):
            raise BusinessRuleViolationError("Expected InboundEmailMessage", error_code="INVALID_PAYLOAD_TYPE")
        return cls.classify_text(text=inbound.body_text, sender_email=inbound.sender_email, subject=inbound.subject)

    @classmethod
    def classify_text(cls, text: str, sender_email: str, subject: str = "") -> ExtractedDemand:
        normalized_email = AccessControlGuard.normalize_email(sender_email)
        full_text = scrub_control_characters(f"{subject}\n{text}".strip())
        order_id = extract_order_id(full_text)
        all_order_ids = extract_all_order_ids(full_text)
        is_threat = detect_legal_threat_or_hostility(full_text)

        if is_threat:
            return ExtractedDemand(
                intent=IntentEnum.OUT_OF_SCOPE,
                order_id=order_id,
                customer_email=normalized_email,
                is_legal_threat_or_aggressive=True,
                sub_queries=(),
            )
        ...
```

```bash
# Validation commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **PreExtractionClassifier (`src/security/pre_extraction.py`)**: Implemented pre-flight deterministic intent and threat extraction.
2. [x] **TC-05 Short-Circuiting**: Missing order IDs on order-dependent inquiries set to `IntentEnum.INFORMATION_MISSING` with 0 tool calls.
3. [x] **TC-11 Hostile Legal Threat Escort**: Litigation and hostility flagged as `OUT_OF_SCOPE` with `is_legal_threat_or_aggressive=True`.
4. [x] **Functional Intent Family Grouping**: Accurately distinguishes single complex inquiries from true multi-intent `MIXED_QUERY` requests.
5. [x] **Sub-Query Decomposition**: Splits compound queries into immutable tuple clauses in `ExtractedDemand`.
6. [x] **Comprehensive Test Suite (`tests/unit/test_pre_extraction.py`)**: 174 tests passing across nominal paths, error boundaries, and multilingual inputs.
7. [x] **Quality Gates Verified**: `make lint`, `make typecheck` (Mypy strict), and `make test` passing 100%.
