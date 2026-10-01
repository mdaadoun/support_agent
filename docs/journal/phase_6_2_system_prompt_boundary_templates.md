# Session 6.2: System Prompt & Boundary Templates
**Date:** 2026-09-29

*Implemented hardened system prompts (`AGENT_SYSTEM_PROMPT`, `EXTRACTION_SYSTEM_PROMPT`, `RESPONSE_SYNTHESIS_SYSTEM_PROMPT`), dynamic observation formatting (`format_observation`, `format_tool_trace_observation`), input sanitization wrapping (`format_user_prompt`), and the centralized `PromptManager` facade in `src/agent/prompts.py`. Enforced strict operational boundaries: passive `<user_email>` XML delimiters, zero LLM financial authority, tool observation grounding, and automatic human escalation paths.*

---

### 1. 🎓 Concepts Introduced
- **Static Boundary System Prompts:** Hardened, immutable prompt templates containing core domain invariants that never mutate dynamically at runtime, preventing instruction drift and prompt injection.
- **Passive Input Parsing (`<user_email>`):** An architectural delimiter constraint explicitly informing the LLM that content within XML envelope tags is raw user data to be analyzed, never executable system instructions or policy overrides.
- **Zero LLM Financial Authority:** An inviolable domain boundary forbidding the model from calculating, granting, negotiating, or promising any monetary compensation, refund, or voucher; all figures must originate from deterministic domain tools.
- **Structured Tool Observation Blocks (`<tool_observation>`):** Standardized XML containers wrapping certified tool outputs (`tool`, `success`, `error_code`) and JSON payloads into the ReAct reasoning context.
- **PromptManager Facade:** A centralized orchestration helper responsible for sanitizing inbound messages, binding order metadata, and assembling chronological multi-turn ReAct histories.
- **Response Synthesis Grounding:** Directing the model to compose final customer-facing responses based solely on verified tool observations without external speculation or hallucination.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Static Hardened Boundary System Prompts vs Dynamic Runtime Assembly
- **Option 1:** Dynamically generate and modify system prompt rules on each request turn.
- **Option 2 (Selected):** Maintain static, hardened system prompt constants combined with dynamic XML observation blocks.
- **Rationale:** Freezing core boundary constraints in immutable static templates prevents accidental prompt drift or leakage, reduces prompt compilation latency, guarantees that zero financial authority and injection defenses remain inviolable across every session turn, and simplifies unit test verification.

#### Decision: Structured XML Boundary Framing (<user_email>, <tool_observation>) vs JSON/Markdown Blocks
- **Option 1:** Wrap user input and tool outputs in JSON strings or Markdown triple backticks.
- **Option 2 (Selected):** Wrap untrusted user content and trusted tool observations in dedicated XML boundary tags.
- **Rationale:** Frontier LLMs exhibit superior boundary adherence when separating system instructions from untrusted data using explicit XML tags. XML framing prevents markdown breakout attacks and provides unambiguous semantic namespaces for untrusted user inputs versus trusted, certified tool observations.

#### Decision: Centralized PromptManager Facade vs Ad-Hoc Formatting in Loop Engine
- **Option 1:** Construct prompt strings ad-hoc inside ReActLoopEngine or API routes.
- **Option 2 (Selected):** Centralize prompt templating, history assembly, and boundary wrapping within `PromptManager`.
- **Rationale:** Decouples prompt engineering and message templating from loop execution and network clients. Enables isolated testing of prompt rendering, simplifies future multi-language or personalized prompt variations, and guarantees uniform sanitization before payloads reach LLM inference.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/agent/prompts.py
class PromptManager:
    """Manages prompt templating and boundary wrapping for agent execution."""

    @classmethod
    def build_initial_agent_prompt(
        cls,
        email_body: str,
        detected_intent: CustomerIntent | None = None,
        extracted_order_id: str | None = None,
    ) -> str:
        wrapped_user_email = format_user_prompt(email_body)
        metadata_lines: list[str] = []
        if detected_intent:
            metadata_lines.append(f"Detected Intent: {detected_intent.value}")
        if extracted_order_id:
            metadata_lines.append(f"Extracted Order ID: {extracted_order_id}")

        metadata_block = (
            f"<metadata>\n{chr(10).join(metadata_lines)}\n</metadata>\n\n"
            if metadata_lines
            else ""
        )
        return (
            f"{metadata_block}{wrapped_user_email}\n\n"
            "Analyze the inquiry and decide whether to call a tool or conclude."
        )
```

```bash
# Verification commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **Hardened System Prompts (`src/agent/prompts.py`)**: Authored `AGENT_SYSTEM_PROMPT`, `EXTRACTION_SYSTEM_PROMPT`, and `RESPONSE_SYNTHESIS_SYSTEM_PROMPT` enforcing strict operational guidelines and zero financial authority.
2. [x] **Boundary Formatting Functions (`src/agent/prompts.py`)**: Implemented `format_user_prompt`, `format_observation`, and `format_tool_trace_observation` wrapping content in `<user_email>` and `<tool_observation>` XML envelopes.
3. [x] **Centralized PromptManager Facade (`src/agent/prompts.py`)**: Created `PromptManager` with `build_initial_agent_prompt`, `build_react_history_prompt`, and `build_final_response_prompt`.
4. [x] **Public Package Exports (`src/agent/__init__.py`)**: Exported `PromptManager`, system prompt constants, and formatting helper functions.
5. [x] **Comprehensive Test Suite (`tests/unit/test_prompts.py`)**: Authored 11 unit tests verifying system instructions, tag sanitization, observation parsing, and prompt assembly.
6. [x] **Roadmap Progress (`docs/roadmap.md`)**: Marked Step 6.2 as `[x]`.
